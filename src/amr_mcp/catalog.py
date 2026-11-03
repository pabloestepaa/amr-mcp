"""NCBI Reference Gene Catalog (the AMRFinderPlus database): download, cache and search.

The catalog is a public-domain TSV published by NCBI. It is downloaded once and
cached on disk; it is refreshed when older than ``max_age_days``.
"""

from __future__ import annotations

import csv
import os
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import httpx

CATALOG_URL = (
    "https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/"
    "AMRFinderPlus/database/latest/ReferenceGeneCatalog.txt"
)

# Columns exposed to clients. The raw file has more (coordinates, strands...)
# that are rarely useful to an LLM and only bloat responses.
PUBLIC_FIELDS = (
    "allele",
    "gene_family",
    "product_name",
    "scope",
    "type",
    "subtype",
    "class",
    "subclass",
    "whitelisted_taxa",
    "refseq_protein_accession",
    "refseq_nucleotide_accession",
    "genbank_protein_accession",
    "genbank_nucleotide_accession",
    "pubmed_reference",
    "synonyms",
)


def default_cache_dir() -> Path:
    if env := os.environ.get("AMR_MCP_CACHE_DIR"):
        return Path(env)
    return Path.home() / ".cache" / "amr-mcp"


@dataclass
class Catalog:
    rows: list[dict[str, str]]

    @classmethod
    def from_file(cls, path: Path) -> Catalog:
        with path.open(newline="", encoding="utf-8") as fh:
            rows = [dict(r) for r in csv.DictReader(fh, delimiter="\t")]
        return cls(rows)

    @property
    def db_version(self) -> str:
        return self.rows[0].get("db_version", "unknown") if self.rows else "empty"

    def info(self) -> dict:
        return {
            "source": CATALOG_URL,
            "db_version": self.db_version,
            "total_entries": len(self.rows),
            "by_type": dict(Counter(r["type"] for r in self.rows)),
            "by_scope": dict(Counter(r["scope"] for r in self.rows)),
        }

    def drug_classes(self) -> list[dict]:
        counts = Counter(r["class"] for r in self.rows if r["class"])
        return [{"class": c, "entries": n} for c, n in counts.most_common()]

    def search(
        self,
        query: str | None = None,
        drug_class: str | None = None,
        subclass: str | None = None,
        organism: str | None = None,
        element_type: str | None = None,
        limit: int = 25,
        group_by_family: bool = False,
    ) -> dict:
        q = query.lower() if query else None
        organism_key = organism.replace(" ", "_").lower() if organism else None

        def matches(r: dict[str, str]) -> bool:
            if q and not any(
                q in r[f].lower() for f in ("allele", "gene_family", "product_name", "synonyms")
            ):
                return False
            if drug_class and drug_class.lower() not in r["class"].lower():
                return False
            if subclass and subclass.lower() not in r["subclass"].lower():
                return False
            if element_type and element_type.upper() != r["type"]:
                return False
            if organism_key:
                # Entries with no whitelisted taxa apply to any organism.
                allowed = _taxa(r["whitelisted_taxa"])
                if allowed and not any(organism_key.startswith(t) for t in allowed):
                    return False
                if any(organism_key.startswith(t) for t in _taxa(r["blacklisted_taxa"])):
                    return False
            return True

        hits = [r for r in self.rows if matches(r)]
        if group_by_family:
            families: dict[str, list[dict[str, str]]] = {}
            for r in hits:
                families.setdefault(r["gene_family"], []).append(r)
            ranked = sorted(families.items(), key=lambda kv: -len(kv[1]))
            return {
                "total_matches": len(hits),
                "family_count": len(families),
                "returned": min(len(families), limit),
                "families": [
                    {
                        "gene_family": fam,
                        "entries": len(rows),
                        "example": rows[0]["allele"] or rows[0]["product_name"],
                        "subclasses": sorted({r["subclass"] for r in rows if r["subclass"]}),
                    }
                    for fam, rows in ranked[:limit]
                ],
            }
        return {
            "total_matches": len(hits),
            "returned": min(len(hits), limit),
            "results": [_public(r) for r in hits[:limit]],
        }

    def get(self, name: str) -> dict:
        """Exact lookup by allele (e.g. blaKPC-2) or gene family (e.g. blaKPC)."""
        key = name.lower()
        alleles = [r for r in self.rows if r["allele"].lower() == key]
        if alleles:
            return {"match": "allele", "entries": [_public(r) for r in alleles]}
        family = [r for r in self.rows if r["gene_family"].lower() == key]
        if not family:
            return {"match": None, "entries": []}
        named = [r["allele"] for r in family if r["allele"]]
        return {
            "match": "gene_family",
            "gene_family": family[0]["gene_family"],
            "allele_count": len(named),
            "alleles": named[:200],
            "classes": sorted({r["class"] for r in family if r["class"]}),
            "subclasses": sorted({r["subclass"] for r in family if r["subclass"]}),
            "example_entry": _public(family[0]),
        }


def _taxa(field: str) -> list[str]:
    # Taxa are genus or Genus_species names, comma-separated when there are several.
    return [t.strip().lower() for t in field.split(",") if t.strip()]


def _public(row: dict[str, str]) -> dict[str, str]:
    return {f: row[f] for f in PUBLIC_FIELDS if row.get(f)}


async def load_catalog(
    cache_dir: Path | None = None,
    max_age_days: float = 30,
    client: httpx.AsyncClient | None = None,
) -> Catalog:
    cache_dir = cache_dir or default_cache_dir()
    path = cache_dir / "ReferenceGeneCatalog.txt"
    stale = not path.exists() or (time.time() - path.stat().st_mtime) > max_age_days * 86400
    if stale:
        try:
            await _download(path, client)
        except httpx.HTTPError:
            # Offline or NCBI down: fall back to the stale copy if we have one.
            if not path.exists():
                raise
    return Catalog.from_file(path)


async def _download(path: Path, client: httpx.AsyncClient | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=60, follow_redirects=True)
    try:
        resp = await client.get(CATALOG_URL)
        resp.raise_for_status()
        tmp.write_bytes(resp.content)
        tmp.replace(path)
    finally:
        if owns_client:
            await client.aclose()
