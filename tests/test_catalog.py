from pathlib import Path

import pytest

from amr_mcp.catalog import Catalog

FIXTURE = Path(__file__).parent / "fixtures" / "catalog_sample.tsv"


@pytest.fixture
def catalog() -> Catalog:
    return Catalog.from_file(FIXTURE)


def test_info(catalog):
    info = catalog.info()
    assert info["total_entries"] == 9
    assert info["by_type"]["AMR"] == 7
    assert info["db_version"] != "unknown"


def test_drug_classes_sorted_by_count(catalog):
    classes = catalog.drug_classes()
    assert classes[0] == {"class": "BETA-LACTAM", "entries": 3}


def test_search_by_text_is_case_insensitive(catalog):
    result = catalog.search(query="kpc")
    assert result["total_matches"] == 3
    assert {r["allele"] for r in result["results"]} == {"blaKPC-2", "blaKPC-3", "blaKPC-20"}


def test_search_limit(catalog):
    result = catalog.search(query="kpc", limit=1)
    assert result["total_matches"] == 3
    assert result["returned"] == 1


def test_search_by_class_and_type(catalog):
    assert catalog.search(drug_class="colistin")["results"][0]["allele"] == "mcr-1.1"
    assert catalog.search(element_type="VIRULENCE")["total_matches"] == 1


def test_group_by_family(catalog):
    result = catalog.search(drug_class="beta-lactam", group_by_family=True)
    assert result["total_matches"] == 3
    assert result["families"] == [
        {"gene_family": "blaKPC", "entries": 3, "example": "blaKPC-2", "subclasses": ["CARBAPENEM"]}
    ]


def test_organism_whitelist(catalog):
    # Acinetobacter-only point mutation is excluded for E. coli but included for A. baumannii.
    assert "adeL_G27R" not in _alleles(catalog.search(organism="Escherichia coli", limit=100))
    assert "adeL_G27R" in _alleles(catalog.search(organism="Acinetobacter baumannii", limit=100))
    # Genus-level whitelist matches a species of that genus.
    assert "16S_A523C" in _alleles(catalog.search(organism="Escherichia coli", limit=100))


def test_organism_blacklist(catalog):
    families = {r["gene_family"] for r in catalog.search(organism="Escherichia coli", limit=100)["results"]}
    assert "arsB" not in families
    assert "arsB" in {r["gene_family"] for r in catalog.search(organism="Salmonella enterica", limit=100)["results"]}


def test_get_allele(catalog):
    result = catalog.get("BLAKPC-2")
    assert result["match"] == "allele"
    entry = result["entries"][0]
    assert entry["refseq_protein_accession"].startswith("WP_")
    # Empty columns are dropped to keep responses small.
    assert "whitelisted_taxa" not in entry


def test_get_gene_family(catalog):
    result = catalog.get("blaKPC")
    assert result["match"] == "gene_family"
    assert result["allele_count"] == 3
    assert result["subclasses"] == ["CARBAPENEM"]


def test_get_unknown(catalog):
    assert catalog.get("notagene")["match"] is None


def _alleles(result: dict) -> set[str]:
    return {r.get("allele") for r in result["results"]}
