# amr-mcp

An [MCP](https://modelcontextprotocol.io) server that lets AI assistants (Claude, Codex, Cursor…) query
**antimicrobial resistance (AMR)** data from public, free sources:

- **NCBI Reference Gene Catalog**, the curated database behind
  [AMRFinderPlus](https://github.com/ncbi/amr): ~11,500 AMR genes, point mutations, stress and virulence genes
- **NCBI E-utilities**: protein and nucleotide sequences, PubMed references
- **UniProtKB**: protein function, keywords and cross-references
- **AMRFinderPlus** (optional, if installed locally): screen your own genomes

All data sources are public domain or freely accessible; no API keys are required.

## Example questions

> Which carbapenemases are reported in *Klebsiella pneumoniae*, and what is the original paper for KPC-2?

> Give me the protein sequence of mcr-1.1 and its UniProt function annotation.

> Run AMRFinderPlus on `~/data/isolate_17.fasta` as *Escherichia* and explain the hits by drug class.

## Tools

| Tool | What it does |
|---|---|
| `search_amr_genes` | Search by text, drug class, subclass, organism or element type |
| `get_amr_gene` | Exact record for an allele (`blaKPC-2`) or summary of a family (`blaKPC`) |
| `list_drug_classes` | Drug classes and how many catalog entries each has |
| `catalog_info` | Catalog version and size |
| `fetch_sequence` | Protein or nucleotide FASTA from NCBI by accession |
| `get_pubmed_references` | Title, journal, authors and DOI for PubMed IDs |
| `search_uniprot` / `get_uniprot_entry` | UniProtKB search and entry details |
| `run_amrfinder` | Run a local AMRFinderPlus install on a FASTA file |

## Installation

```bash
pip install git+https://github.com/pabloestepaa/amr-mcp
```

### Claude Code

```bash
claude mcp add amr -- amr-mcp
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "amr": { "command": "amr-mcp" }
  }
}
```

## Configuration

| Variable | Purpose |
|---|---|
| `NCBI_API_KEY` | Optional, free. Raises the NCBI rate limit from 3 to 10 requests/s |
| `NCBI_EMAIL` | Optional. Contact e-mail NCBI asks tools to send |
| `AMR_MCP_CACHE_DIR` | Where the catalog is cached (default `~/.cache/amr-mcp`, refreshed every 30 days) |

To enable `run_amrfinder`: `conda install -c bioconda ncbi-amrfinderplus && amrfinder -u`.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -m "not network"   # offline tests
.venv/bin/pytest                    # also hits the live NCBI/UniProt APIs
```

## Data licensing

The NCBI Reference Gene Catalog and NCBI sequence data are US government works in the public domain.
UniProt data is available under CC BY 4.0. Please cite the original sources when you publish results:

- Feldgarden M, et al. *AMRFinderPlus and the Reference Gene Catalog facilitate examination of the
  genomic links among antimicrobial resistance, stress response, and virulence.* Sci Rep. 2021.
- The UniProt Consortium. *UniProt: the Universal Protein Knowledgebase.* Nucleic Acids Res.

## License

MIT

---

Developed with AI assistance (Claude Code); all code reviewed and tested by the author.
