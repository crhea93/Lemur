import importlib
import sys
from pathlib import Path

if __package__:
    _config_mod = importlib.import_module(".config", package=__package__)
    _pipeline_mod = importlib.import_module(".pipeline", package=__package__)
else:
    _config_mod = importlib.import_module("config")
    _pipeline_mod = importlib.import_module("pipeline")


def expect_paths(inputs):
    root = Path(inputs["home_dir"])
    name = inputs["name"]
    out = root / name
    expected = [
        out / "Additional.txt",
        out / "broad_flux.img",
        out / "broad_thresh.expmap",
        out / "bkg.reg",
    ]
    if str(inputs.get("merge", "")).lower() == "true":
        expected.append(out / "merged_evt.fits")
    return expected


def smoke(input_path):
    inputs, _merge, _env = _config_mod.load_config(input_path)
    _pipeline_mod.run_pipeline(input_path)
    missing = [p for p in expect_paths(inputs) if not p.exists()]
    if missing:
        print("Smoke test failed. Missing outputs:")
        for path in missing:
            print(f" - {path}")
        return 1
    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python smoke_test.py /path/to/input.i")
        sys.exit(2)
    sys.exit(smoke(sys.argv[1]))
