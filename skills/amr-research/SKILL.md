---
name: amr-research
description: Answer antimicrobial resistance (AMR) questions with the amr-mcp server, which queries the NCBI Reference Gene Catalog (the AMRFinderPlus database), NCBI E-utilities and UniProt. Use when the user asks about a resistance gene or allele (blaKPC-2, mcr-1, vanA, NDM, OXA-48...), a gene family, a drug class or resistance mechanism, which species carry a resistance gene, the protein or nucleotide sequence of an AMR gene, the paper that first described it, or wants to screen a genome or proteome FASTA for resistance genes with AMRFinderPlus.
---

# AMR research with amr-mcp

The amr-mcp tools answer questions about antimicrobial resistance genes from curated public data.
Prefer them over memory: allele numbering, drug classes and accessions change between catalog
releases, and the catalog is the reference AMRFinderPlus itself uses.

## Setup check

The tools are `search_amr_genes`, `get_amr_gene`, `list_drug_classes`, `catalog_info`,
`fetch_sequence`, `get_protein_hosts`, `get_pubmed_references`, `search_uniprot`,
`get_uniprot_entry` and `run_amrfinder` (often shown with a server prefix such as `mcp__amr__`).
If none are available, tell the user to install the server and restart the agent:

```bash
claude mcp add amr -- uvx amr-mcp
```

Other clients: run `uvx amr-mcp` (or `pipx install amr-mcp`) as a stdio MCP server.
No API keys are needed. The first call downloads the catalog (a few MB) and caches it for 30 days.

## Workflows

**A specific gene or allele** ("tell me about blaKPC-2")
1. `get_amr_gene` with the exact name. An allele (`blaKPC-2`) returns its full record; a family
   (`blaKPC`) returns the list of alleles. If it is not found, fall back to `search_amr_genes`
   with a shorter query (`KPC`).
2. From the record, use `refseq_protein_accession` (a `WP_` accession) for sequences and hosts,
   and `pubmed_reference` for literature.

**Which species carry it**
- The catalog says what a gene is, not where it occurs. Call `get_protein_hosts` with the
  allele's `WP_` accession; it reports the species NCBI has sequenced that exact protein in,
  with record counts.
- Do not use the `organism` filter of `search_amr_genes` for this. It only drops entries the
  catalog restricts to other taxa, and most acquired genes have no restriction.

**Sequence**: `fetch_sequence` with the RefSeq accession; `kind="protein"` for `WP_`/`NP_`,
`kind="nucleotide"` for `NG_`/`NZ_`/`NC_` accessions.

**Original paper**: `get_pubmed_references` with the IDs from `pubmed_reference`
(it can hold several, comma-separated). Cite title, journal, year and DOI.

**Protein function and structure links**: `search_uniprot` (UniProt query syntax, e.g.
`gene:mcr-1`; set `reviewed_only=true` for Swiss-Prot), then `get_uniprot_entry`.

**Overviews by drug class or mechanism** ("which carbapenemase families exist?")
1. `list_drug_classes` if unsure of the exact name. Classes are upper-case: `BETA-LACTAM`,
   `AMINOGLYCOSIDE`, `COLISTIN`, `GLYCOPEPTIDE`... Subclasses too: `CARBAPENEM`, `CEPHALOSPORIN`.
2. `search_amr_genes` with `drug_class`/`subclass` and `group_by_family=true`. Without grouping a
   broad search returns hundreds of near-identical alleles; grouping gives one row per family
   with its entry count.

**Screening a genome** (`run_amrfinder`)
- Needs AMRFinderPlus installed locally (`conda install -c bioconda ncbi-amrfinderplus && amrfinder -u`).
  If the tool reports it is missing, give the user that command rather than retrying.
- Pass an absolute path. Use `sequence_type="protein"` for proteomes.
- Pass `organism` (e.g. `Escherichia`, `Klebsiella_pneumoniae`, `Salmonella`) whenever the species
  is known: it enables point-mutation screening (gyrA, parC, pmrB...), which is skipped otherwise.
- Explain hits grouped by drug class, and separate acquired genes from point mutations.

## Answering

- Distinguish `type` AMR from STRESS and VIRULENCE entries, and `scope` core from plus
  (plus entries are outside the core AMR set AMRFinderPlus screens by default).
- Report what the data shows, not inferred phenotype: a gene being present does not by itself
  prove clinical resistance, and `get_protein_hosts` counts sequenced records, which reflects
  sampling effort as much as prevalence.
- Mention the catalog version (`catalog_info`) when exact counts matter.
- When results go into a publication, point the user to the citations in the amr-mcp README
  (Feldgarden et al. 2021 for AMRFinderPlus and the catalog; UniProt Consortium).
