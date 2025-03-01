import pytest

from ..citekey import CiteKey
from ..curie import Handler_CURIE, curie_to_url, get_bioregistry, get_prefix_to_resource


def test_bioregistry_resource_patterns():
    """
    Can find issues like https://github.com/biopragmatics/bioregistry/issues/242
    """
    registry = get_bioregistry(compile_patterns=True)
    assert isinstance(registry, list)
    reports = list()
    for resource in registry:
        assert resource["prefix"]  # ensure prefix field exists
        if "example" in resource and "pattern" in resource:
            prefix = resource["prefix"]
            example = resource["example"]
            handler = Handler_CURIE(prefix)
            example_curie = CiteKey(f"{prefix}:{example}")
            report = handler.inspect(example_curie)
            if report:
                reports.append(report)
    print("\n".join(reports))
    assert not reports


def test_get_prefix_to_resource():
    prefix_to_resource = get_prefix_to_resource()
    assert isinstance(prefix_to_resource, dict)
    assert "doid" in prefix_to_resource
    resource = prefix_to_resource["doid"]
    resource["preferred_prefix"] = "DOID"


@pytest.mark.parametrize(
    "curie, expected",
    [
        ("doi:10.1038/nbt1156", "https://doi.org/10.1038/nbt1156"),
        ("DOI:10.1038/nbt1156", "https://doi.org/10.1038/nbt1156"),
        ("arXiv:0807.4956v1", "https://arxiv.org/abs/0807.4956v1"),
        (
            "taxonomy:9606",
            "https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?mode=Info&id=9606",
        ),
        ("CHEBI:36927", "https://www.ebi.ac.uk/chebi/searchId.do?chebiId=CHEBI:36927"),
        ("ChEBI:36927", "https://www.ebi.ac.uk/chebi/searchId.do?chebiId=CHEBI:36927"),
        (
            "DOID:11337",
            "https://www.ebi.ac.uk/ols/ontologies/doid/terms?obo_id=DOID:11337",
        ),
        (
            "doid:11337",
            "https://www.ebi.ac.uk/ols/ontologies/doid/terms?obo_id=DOID:11337",
        ),
        (
            "clinicaltrials:NCT00222573",
            "https://clinicaltrials.gov/ct2/show/NCT00222573",
        ),
        (
            "clinicaltrials:NCT04292899",
            "https://clinicaltrials.gov/ct2/show/NCT04292899",
        ),
        # formerly afflicted by https://github.com/identifiers-org/identifiers-org.github.io/issues/99#issuecomment-614690283
        pytest.param(
            "gramene.growthstage:0007133",
            "http://www.gramene.org/db/ontology/search?id=GRO:0007133",
            id="gramene.growthstage",
        ),
    ],
)
def test_curie_to_url(curie, expected):
    url = curie_to_url(curie)
    assert url == expected


def test_curie_to_url_bad_curie():
    with pytest.raises(ValueError):
        curie_to_url("this.is.not:a_curie")
