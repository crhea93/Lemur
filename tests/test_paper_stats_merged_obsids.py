import gzip
import importlib.util
from pathlib import Path

from astropy.io import fits

_spec = importlib.util.spec_from_file_location(
    "paper_stats", Path(__file__).resolve().parents[1] / "scripts" / "paper_stats.py"
)
paper_stats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paper_stats)


def _header(*history):
    header = fits.Header()
    for line in history:
        header.add_history(line)
    return header


def test_stack_file_read_despite_stck_cards_and_decoy(tmp_path):
    # merge_obs records the stack file's name, then its contents as STCK cards.
    (tmp_path / "merge_inputs.lis").write_text(
        "3244/repro/acisf3244_repro_evt2_uncontam.fits\n"
        "11725/repro/acisf11725_repro_evt2_uncontam.fits.gz\n"
    )
    # A file named like the last STCK entry must not be mistaken for the list.
    with gzip.open(tmp_path / "acisf11725_repro_evt2_uncontam.fits.gz", "wb") as fh:
        fh.write(b"not a stack file")
    header = _header(
        "PARM  :infiles=@-Abell1682/merge_inputs.lis",
        "STCK  :3244/repro/acisf3244_repro_evt2_uncontam.fits",
        "STCK  :11725/repro/acisf11725_repro_evt2_uncontam.fits.gz",
        "PARM  :outroot=Abell1682/",
    )
    assert paper_stats.merged_obsids(header, tmp_path / "broad_flux.img") == {3244, 11725}


def test_single_obsid_image_uses_obs_id():
    header = fits.Header()
    header["OBS_ID"] = "4977"
    assert paper_stats.merged_obsids(header) == {4977}
