import sys
import types

import Pipeline  # noqa: F401  (puts Pipeline/ on sys.path)

# Merge.py star-imports CIAO tools; the helper under test needs none of them.
if "ciao_contrib.runtool" not in sys.modules:
    stub = types.ModuleType("ciao_contrib.runtool")
    setattr(stub, "__all__", [])
    sys.modules.setdefault("ciao_contrib", types.ModuleType("ciao_contrib"))
    sys.modules["ciao_contrib.runtool"] = stub

from Preliminary.Merge import has_cleaned_events  # noqa: E402


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_uncleaned_obsid(tmp_path):
    _touch(tmp_path / "1234" / "primary" / "acisf01234N003_evt2.fits.gz")
    assert not has_cleaned_events("1234", tmp_path)


def test_cleaned_plain_or_gzipped(tmp_path):
    _touch(tmp_path / "1234" / "repro" / "acisf1234_repro_evt2.fits")
    _touch(tmp_path / "5678" / "repro" / "acisf5678_repro_evt2_uncontam.fits.gz")
    assert has_cleaned_events("1234", tmp_path)
    assert has_cleaned_events(5678, tmp_path)


def test_cleaned_segments(tmp_path):
    _touch(tmp_path / "4321" / "repro" / "acisf4321_001_repro_evt2.fits.gz")
    assert has_cleaned_events("4321", tmp_path)
