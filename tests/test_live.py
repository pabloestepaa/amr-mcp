"""Smoke tests against the real NCBI and UniProt APIs. Skip with: pytest -m 'not network'."""

import pytest

from amr_mcp.catalog import load_catalog
from amr_mcp.ncbi import NCBIClient
from amr_mcp.uniprot import UniProtClient

pytestmark = pytest.mark.network


async def test_download_full_catalog(tmp_path):
    catalog = await load_catalog(cache_dir=tmp_path)
    assert len(catalog.rows) > 5000
    assert catalog.get("blaKPC-2")["match"] == "allele"


async def test_fetch_kpc2_protein():
    ncbi = NCBIClient()
    try:
        seq = await ncbi.fetch_fasta("WP_004199234.1", "protein")
    finally:
        await ncbi.aclose()
    assert "KPC" in seq["header"]
    assert 280 <= seq["length"] <= 300


async def test_pubmed_summary():
    ncbi = NCBIClient()
    try:
        refs = await ncbi.pubmed_summaries(["12615876"])
    finally:
        await ncbi.aclose()
    assert refs[0]["pmid"] == "12615876"
    assert refs[0]["title"]


async def test_uniprot_search_and_entry():
    uniprot = UniProtClient()
    try:
        found = await uniprot.search("gene:KPC-2", reviewed_only=True, limit=3)
        assert found["results"]
        entry = await uniprot.entry(found["results"][0]["accession"])
    finally:
        await uniprot.aclose()
    assert entry["sequence"]
    assert entry["reviewed"] is True
