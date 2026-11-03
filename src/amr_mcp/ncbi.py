"""Minimal NCBI E-utilities client (efetch / esummary).

Without an API key NCBI allows 3 requests/second; with one (free, set
``NCBI_API_KEY``) it allows 10. Requests are spaced accordingly.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from collections import Counter

import httpx

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL_NAME = "amr-mcp"

# RefSeq / GenBank / WGS accessions, optionally versioned (WP_004199234.1, NG_049253.1, AY034847).
ACCESSION_RE = re.compile(r"^[A-Z]{1,6}_?[A-Z0-9]*\d+(\.\d+)?$")
MAX_SEQUENCE_CHARS = 200_000


class NCBIClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30, follow_redirects=True)
        self._api_key = os.environ.get("NCBI_API_KEY")
        self._email = os.environ.get("NCBI_EMAIL")
        self._min_interval = 0.11 if self._api_key else 0.34
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, endpoint: str, params: dict[str, str]) -> httpx.Response:
        params = {**params, "tool": TOOL_NAME}
        if self._api_key:
            params["api_key"] = self._api_key
        if self._email:
            params["email"] = self._email
        async with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()
        resp = await self._client.get(f"{EUTILS}/{endpoint}", params=params)
        resp.raise_for_status()
        return resp

    async def fetch_fasta(self, accession: str, kind: str) -> dict:
        accession = accession.strip().upper()
        if not ACCESSION_RE.match(accession):
            raise ValueError(f"'{accession}' does not look like an NCBI accession")
        db = {"protein": "protein", "nucleotide": "nuccore"}[kind]
        resp = await self._get(
            "efetch.fcgi", {"db": db, "id": accession, "rettype": "fasta", "retmode": "text"}
        )
        fasta = resp.text.strip()
        if not fasta.startswith(">"):
            raise ValueError(f"NCBI returned no FASTA for {accession} in db={db}")
        header, _, body = fasta.partition("\n")
        seq = body.replace("\n", "")
        truncated = len(seq) > MAX_SEQUENCE_CHARS
        return {
            "accession": accession,
            "db": db,
            "header": header[1:],
            "length": len(seq),
            "truncated": truncated,
            "sequence": seq[:MAX_SEQUENCE_CHARS],
        }

    async def protein_hosts(self, accession: str, top: int = 15) -> dict:
        """Organisms carrying this exact protein, from NCBI Identical Protein Groups."""
        accession = accession.strip().upper()
        if not ACCESSION_RE.match(accession):
            raise ValueError(f"'{accession}' does not look like an NCBI accession")
        resp = await self._get(
            "efetch.fcgi", {"db": "ipg", "id": accession, "rettype": "ipg", "retmode": "text"}
        )
        return summarize_ipg(accession, resp.text, top)

    async def pubmed_summaries(self, pmids: list[str]) -> list[dict]:
        ids = [p.strip() for p in pmids if p.strip().isdigit()]
        if not ids:
            raise ValueError("Provide numeric PubMed IDs")
        resp = await self._get(
            "esummary.fcgi", {"db": "pubmed", "id": ",".join(ids[:50]), "retmode": "json"}
        )
        result = resp.json().get("result", {})
        out = []
        for pmid in result.get("uids", []):
            doc = result[pmid]
            out.append(
                {
                    "pmid": pmid,
                    "title": doc.get("title"),
                    "journal": doc.get("fulljournalname") or doc.get("source"),
                    "pubdate": doc.get("pubdate"),
                    "authors": [a["name"] for a in doc.get("authors", [])][:6],
                    "doi": next(
                        (i["value"] for i in doc.get("articleids", []) if i["idtype"] == "doi"),
                        None,
                    ),
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                }
            )
        return out


def summarize_ipg(accession: str, report: str, top: int = 15) -> dict:
    """Count IPG report rows by species. Rows are sequence records, one per contig or plasmid."""
    lines = report.strip().splitlines()
    if not lines or not lines[0].startswith("Id\t"):
        raise ValueError(f"NCBI has no identical protein group for {accession}")
    header = lines[0].split("\t")
    org_col, nuc_col = header.index("Organism"), header.index("Nucleotide Accession")
    species: Counter[str] = Counter()
    records = set()
    for line in lines[1:]:
        cols = line.split("\t")
        if len(cols) <= max(org_col, nuc_col):
            continue
        records.add(cols[nuc_col])
        # "Klebsiella pneumoniae subsp. pneumoniae" counts as Klebsiella pneumoniae.
        species[" ".join(cols[org_col].split()[:2])] += 1
    total = sum(species.values())
    return {
        "accession": accession,
        "source": "NCBI Identical Protein Groups",
        "note": "Counts are sequence records in NCBI, so they reflect sequencing effort as well as prevalence.",
        "total_records": total,
        "nucleotide_records": len(records),
        "species_count": len(species),
        "top_species": [
            {"species": s, "records": n, "percent": round(100 * n / total, 1)}
            for s, n in species.most_common(top)
        ],
    }
