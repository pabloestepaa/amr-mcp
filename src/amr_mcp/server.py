"""MCP server exposing antimicrobial-resistance data from public NCBI and UniProt sources."""

from __future__ import annotations

import asyncio
import functools
from typing import Annotated, Any, Literal

import httpx

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from . import amrfinder
from .catalog import Catalog, load_catalog
from .ncbi import NCBIClient
from .uniprot import UniProtClient

INSTRUCTIONS = """\
Tools for antimicrobial resistance (AMR) research backed by public databases:
the NCBI Reference Gene Catalog (the AMRFinderPlus database), NCBI E-utilities and UniProt.
Typical flow: search_amr_genes or get_amr_gene -> fetch_sequence with the RefSeq accession
-> get_pubmed_references with the pubmed_reference IDs. Drug classes are upper-case
(e.g. BETA-LACTAM, AMINOGLYCOSIDE); call list_drug_classes to see them all.
"""

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

mcp = MCPServer("amr-mcp", instructions=INSTRUCTIONS)


class _State:
    """Lazily created shared clients; the catalog is only downloaded on first use."""

    def __init__(self) -> None:
        self.catalog: Catalog | None = None
        self._catalog_lock = asyncio.Lock()
        self.ncbi = NCBIClient()
        self.uniprot = UniProtClient()

    async def get_catalog(self) -> Catalog:
        async with self._catalog_lock:
            if self.catalog is None:
                self.catalog = await load_catalog()
            return self.catalog


state = _State()


def _user_errors(fn):
    """Surface expected failures to the model; MCPServer hides plain exceptions' text."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except (ValueError, RuntimeError) as exc:
            raise ToolError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise ToolError(f"{exc.request.url.host} returned HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ToolError(f"Network error talking to {exc.request.url.host}: {exc}") from exc

    return wrapper


@mcp.tool(annotations=READ_ONLY)
@_user_errors
async def catalog_info() -> dict[str, Any]:
    """Version and size of the NCBI Reference Gene Catalog in use."""
    return (await state.get_catalog()).info()


@mcp.tool(annotations=READ_ONLY)
@_user_errors
async def list_drug_classes() -> dict[str, Any]:
    """All drug classes in the catalog with the number of entries for each."""
    return {"drug_classes": (await state.get_catalog()).drug_classes()}


@mcp.tool(annotations=READ_ONLY)
@_user_errors
async def search_amr_genes(
    query: Annotated[
        str | None, Field(description="Text in allele, gene family, product name or synonyms, e.g. 'KPC', 'mcr', 'carbapenemase'")
    ] = None,
    drug_class: Annotated[str | None, Field(description="e.g. BETA-LACTAM, COLISTIN, AMINOGLYCOSIDE")] = None,
    subclass: Annotated[str | None, Field(description="e.g. CARBAPENEM, CEPHALOSPORIN")] = None,
    organism: Annotated[
        str | None, Field(description="Restrict to entries valid for this organism, e.g. 'Klebsiella pneumoniae'")
    ] = None,
    element_type: Annotated[Literal["AMR", "STRESS", "VIRULENCE"] | None, Field(description="Element type")] = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 25,
) -> dict[str, Any]:
    """Search the NCBI Reference Gene Catalog of AMR, stress and virulence genes and point mutations."""
    catalog = await state.get_catalog()
    return catalog.search(query, drug_class, subclass, organism, element_type, limit)


@mcp.tool(annotations=READ_ONLY)
@_user_errors
async def get_amr_gene(
    name: Annotated[str, Field(description="Exact allele (e.g. 'blaKPC-2') or gene family (e.g. 'blaKPC')")],
) -> dict[str, Any]:
    """Full catalog record for an allele, or a summary of all alleles in a gene family."""
    result = (await state.get_catalog()).get(name)
    if result["match"] is None:
        raise ValueError(f"'{name}' is not in the catalog; try search_amr_genes for a fuzzy match")
    return result


@mcp.tool(annotations=READ_ONLY)
@_user_errors
async def fetch_sequence(
    accession: Annotated[str, Field(description="NCBI accession, e.g. WP_004199234.1 or NG_049253.1")],
    kind: Literal["protein", "nucleotide"] = "protein",
) -> dict[str, Any]:
    """Fetch a protein or nucleotide sequence from NCBI in FASTA form."""
    return await state.ncbi.fetch_fasta(accession, kind)


@mcp.tool(annotations=READ_ONLY)
@_user_errors
async def get_pubmed_references(
    pmids: Annotated[list[str], Field(description="PubMed IDs, e.g. from a catalog entry's pubmed_reference", max_length=50)],
) -> dict[str, Any]:
    """Title, journal, date, authors and DOI for PubMed articles."""
    return {"articles": await state.ncbi.pubmed_summaries(pmids)}


@mcp.tool(annotations=READ_ONLY)
@_user_errors
async def search_uniprot(
    query: Annotated[str, Field(description="UniProt query syntax, e.g. 'gene:KPC-2' or 'carbapenemase AND organism_id:573'")],
    reviewed_only: Annotated[bool, Field(description="Only Swiss-Prot (manually reviewed) entries")] = False,
    limit: Annotated[int, Field(ge=1, le=100)] = 10,
) -> dict[str, Any]:
    """Search UniProtKB proteins."""
    return await state.uniprot.search(query, reviewed_only, limit)


@mcp.tool(annotations=READ_ONLY)
@_user_errors
async def get_uniprot_entry(
    accession: Annotated[str, Field(description="UniProt accession, e.g. Q9F663")],
) -> dict[str, Any]:
    """Function, keywords, cross-references and sequence of a UniProtKB entry."""
    return await state.uniprot.entry(accession)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
@_user_errors
async def run_amrfinder(
    fasta_path: Annotated[str, Field(description="Absolute path to a local FASTA file")],
    sequence_type: Literal["nucleotide", "protein"] = "nucleotide",
    organism: Annotated[
        str | None, Field(description="Enables point-mutation screening, e.g. 'Escherichia', 'Klebsiella_pneumoniae'")
    ] = None,
) -> dict[str, Any]:
    """Screen a local genome or proteome for AMR genes with AMRFinderPlus (must be installed locally)."""
    return await amrfinder.run(fasta_path, sequence_type, organism)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
