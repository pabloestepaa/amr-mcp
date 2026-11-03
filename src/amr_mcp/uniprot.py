"""Minimal UniProtKB REST client."""

from __future__ import annotations

import httpx

UNIPROT = "https://rest.uniprot.org/uniprotkb"
SEARCH_FIELDS = "accession,id,protein_name,gene_names,organism_name,length,reviewed"


class UniProtClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30, follow_redirects=True)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, reviewed_only: bool = False, limit: int = 10) -> dict:
        q = f"({query}) AND (reviewed:true)" if reviewed_only else query
        resp = await self._client.get(
            f"{UNIPROT}/search",
            params={"query": q, "fields": SEARCH_FIELDS, "format": "json", "size": str(limit)},
        )
        resp.raise_for_status()
        results = [_summarize(e) for e in resp.json().get("results", [])]
        return {
            "query": q,
            "total_matches": int(resp.headers.get("x-total-results", len(results))),
            "results": results,
        }

    async def entry(self, accession: str) -> dict:
        resp = await self._client.get(f"{UNIPROT}/{accession.strip()}", params={"format": "json"})
        if resp.status_code in (400, 404):
            raise ValueError(f"UniProt entry '{accession}' not found")
        resp.raise_for_status()
        e = resp.json()
        comments = {
            c["commentType"]: " ".join(t["value"] for t in c.get("texts", []))
            for c in e.get("comments", [])
            if c.get("texts")
        }
        return {
            **_summarize(e),
            "function": comments.get("FUNCTION"),
            "catalytic_activity": comments.get("CATALYTIC ACTIVITY"),
            "keywords": [k["name"] for k in e.get("keywords", [])],
            "cross_references": _xrefs(e, {"RefSeq", "EMBL", "PDB", "Pfam", "InterPro", "CARD"}),
            "sequence": e.get("sequence", {}).get("value"),
            "url": f"https://www.uniprot.org/uniprotkb/{e['primaryAccession']}",
        }


def _summarize(e: dict) -> dict:
    desc = e.get("proteinDescription", {})
    name = (
        desc.get("recommendedName", {}).get("fullName", {}).get("value")
        or next(iter(desc.get("submissionNames", [])), {}).get("fullName", {}).get("value")
    )
    return {
        "accession": e.get("primaryAccession"),
        "entry_name": e.get("uniProtkbId"),
        "protein_name": name,
        "genes": [g["geneName"]["value"] for g in e.get("genes", []) if "geneName" in g],
        "organism": e.get("organism", {}).get("scientificName"),
        "length": e.get("sequence", {}).get("length"),
        "reviewed": e.get("entryType", "").startswith("UniProtKB reviewed"),
    }


def _xrefs(e: dict, dbs: set[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for x in e.get("uniProtKBCrossReferences", []):
        if x["database"] in dbs:
            out.setdefault(x["database"], []).append(x["id"])
    return {k: v[:20] for k, v in out.items()}
