import pytest

from Pipeline import pipeline


def test_parse_obsids_supports_commas_and_spaces_and_dedupes():
    assert pipeline.parse_obsids(["2203,9897", "2203", "  "]) == ["2203", "9897"]


def test_parse_obsids_rejects_invalid_values():
    with pytest.raises(ValueError, match="Invalid OBSID"):
        pipeline.parse_obsids(["2203,not_an_int"])


def test_parse_obsids_requires_at_least_one_value():
    with pytest.raises(ValueError, match="No OBSIDs provided"):
        pipeline.parse_obsids(["", "   "])


def test_extract_redshift_from_text_prefers_explicit_redshift():
    text = """
    some header
    Redshift: 0.0566
    Quality: 2
    """
    assert pipeline._extract_redshift_from_text(text) == 0.0566


def test_extract_redshift_from_text_ignores_quality_lines():
    text = """
    Redshift quality: 2
    Quality redshift: 3
    """
    assert pipeline._extract_redshift_from_text(text) is None


def test_parse_args_legacy_mode():
    args = pipeline.parse_args(["inputs/template.i"])
    assert args.input_path == "inputs/template.i"
    assert args.cluster is None
    assert args.obsids is None


def test_parse_args_new_mode():
    args = pipeline.parse_args(["--cluster", "Abell133", "--obsids", "2203,9897"])
    assert args.input_path is None
    assert args.cluster == "Abell133"
    assert args.obsids == ["2203,9897"]


def test_parse_args_rejects_mixed_modes():
    with pytest.raises(SystemExit):
        pipeline.parse_args(
            ["inputs/template.i", "--cluster", "Abell133", "--obsids", "2203"]
        )


def test_parse_args_requires_cluster_and_obsids_together():
    with pytest.raises(SystemExit):
        pipeline.parse_args(["--cluster", "Abell133"])
