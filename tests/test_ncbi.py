import pytest

from amr_mcp.ncbi import summarize_ipg

REPORT = """Id\tSource\tNucleotide Accession\tStart\tStop\tStrand\tProtein\tProtein Name\tOrganism\tStrain\tAssembly
1\tRefSeq\tNC_1.1\t1\t882\t+\tWP_1.1\tKPC-2\tKlebsiella pneumoniae\tA\t
1\tINSDC\tCP1.1\t1\t882\t+\tAB1.1\tKPC-2\tKlebsiella pneumoniae subsp. pneumoniae\tB\t
1\tINSDC\tCP2.1\t1\t882\t-\tAB2.1\tKPC-2\tEscherichia coli\tC\t
"""


def test_summarize_ipg_merges_subspecies():
    result = summarize_ipg("WP_1.1", REPORT)
    assert result["total_records"] == 3
    assert result["species_count"] == 2
    assert result["top_species"][0] == {"species": "Klebsiella pneumoniae", "records": 2, "percent": 66.7}


def test_summarize_ipg_empty_report():
    with pytest.raises(ValueError, match="no identical protein group"):
        summarize_ipg("WP_0.1", "")
