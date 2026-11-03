"""End-to-end tests through an in-process MCP client."""

from pathlib import Path

import pytest
from mcp import Client

from amr_mcp import server
from amr_mcp.catalog import Catalog

FIXTURE = Path(__file__).parent / "fixtures" / "catalog_sample.tsv"

EXPECTED_TOOLS = {
    "catalog_info",
    "list_drug_classes",
    "search_amr_genes",
    "get_amr_gene",
    "fetch_sequence",
    "get_protein_hosts",
    "get_pubmed_references",
    "search_uniprot",
    "get_uniprot_entry",
    "run_amrfinder",
}


@pytest.fixture(autouse=True)
def offline_catalog(monkeypatch):
    monkeypatch.setattr(server.state, "catalog", Catalog.from_file(FIXTURE))


async def test_lists_all_tools():
    async with Client(server.mcp) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
    assert tools == EXPECTED_TOOLS


async def test_search_tool_returns_structured_content():
    async with Client(server.mcp) as client:
        result = await client.call_tool("search_amr_genes", {"query": "KPC", "limit": 2})
    assert not result.is_error
    assert result.structured_content["total_matches"] == 3
    assert len(result.structured_content["results"]) == 2


async def test_unknown_gene_is_a_tool_error():
    async with Client(server.mcp) as client:
        result = await client.call_tool("get_amr_gene", {"name": "notagene"})
    assert result.is_error
    assert "search_amr_genes" in result.content[0].text


async def test_bad_accession_is_rejected_before_any_request():
    async with Client(server.mcp) as client:
        result = await client.call_tool("fetch_sequence", {"accession": "rm -rf /"})
    assert result.is_error
