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


def test_parse_args_backfill_mode():
    args = pipeline.parse_args(["--backfill-missing-coords"])
    assert args.backfill_missing_coords is True
    assert args.cluster is None
    assert args.obsids is None


def test_parse_args_backfill_mode_with_sqlite_override():
    args = pipeline.parse_args(
        ["--backfill-missing-coords", "--sqlite-db", "api/data/lemur.db"]
    )
    assert args.backfill_missing_coords is True
    assert args.sqlite_db == "api/data/lemur.db"


def test_parse_args_backfill_with_input_path():
    args = pipeline.parse_args(["inputs/template.i", "--backfill-missing-coords"])
    assert args.backfill_missing_coords is True
    assert args.input_path == "inputs/template.i"


def test_parse_args_rejects_backfill_with_new_mode():
    with pytest.raises(SystemExit):
        pipeline.parse_args(
            ["--backfill-missing-coords", "--cluster", "Abell133", "--obsids", "2203"]
        )


def test_coerce_coord_value_handles_decimal_and_sexagesimal():
    assert pipeline._coerce_coord_value("150.5", is_ra=True) == 150.5
    assert pipeline._coerce_coord_value("10:00:00", is_ra=True) == 150.0
    assert pipeline._coerce_coord_value("+30:00:00", is_ra=False) == 30.0


def test_coerce_coord_value_rejects_out_of_bounds():
    assert pipeline._coerce_coord_value("361", is_ra=True) is None
    assert pipeline._coerce_coord_value("-91", is_ra=False) is None


def test_coords_from_fits_header_reads_crval_values(tmp_path):
    cards = [
        "SIMPLE  =                    T",
        "BITPIX  =                    8",
        "NAXIS   =                    0",
        "CRVAL1  =             123.456",
        "CRVAL2  =             -22.333",
        "END",
    ]
    header = "".join(card.ljust(80) for card in cards).encode("ascii")
    padding = b" " * (2880 - len(header))
    path = tmp_path / "merged_evt.fits"
    path.write_bytes(header + padding)

    assert pipeline._coords_from_fits_header(str(path)) == (123.456, -22.333)


def test_choose_coordinates_prefers_centroid_values(monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_coordinates", lambda *_a, **_k: (1.0, 2.0))
    assert pipeline.choose_coordinates("Abell133", 3.0, 4.0) == (3.0, 4.0)


def test_choose_coordinates_uses_resolver_when_centroid_missing(monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_coordinates", lambda *_a, **_k: (1.0, 2.0))
    assert pipeline.choose_coordinates("Abell133", None, None) == (1.0, 2.0)


def test_resolve_coordinates_uses_fits_header_when_services_fail(tmp_path, monkeypatch):
    cards = [
        "SIMPLE  =                    T",
        "BITPIX  =                    8",
        "NAXIS   =                    0",
        "RA_NOM  =             200.123",
        "DEC_NOM =             -10.456",
        "END",
    ]
    header = "".join(card.ljust(80) for card in cards).encode("ascii")
    padding = b" " * (2880 - len(header))
    path = tmp_path / "broad_flux.img"
    path.write_bytes(header + padding)

    monkeypatch.setattr(pipeline, "_coords_from_ned", lambda _name: None)
    monkeypatch.setattr(pipeline, "_coords_from_cds", lambda _name: None)

    result = pipeline.resolve_coordinates(
        "UnknownName", fallback_fits_paths=[str(path)]
    )
    assert result == (200.123, -10.456)
