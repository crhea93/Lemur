"""The manifest of a preprocessing run: one row per image, aligned with the arrays.

Columns (besides the identifiers source, name, band and ``index``, the row of
the image in ``inputs_{source}.npy``):

- observing conditions: redshift, exposure_ks, instrument counts, halo
  mass and projection for mocks;
- geometry: center_ra/center_dec/center_method, field_arcsec, field_kpc,
  native_pix_per_output (0.492" ACIS pixels per output pixel; < 1 means the
  field is upsampled), coverage_mean, coverage_core (central quarter);
- intensity: vmin, vmax of the stretch;
- flags: status ("ok" or why the image was skipped), low_coverage,
  upsampled, no_signal (nothing above vmin), and ``usable`` combining them
  under the run's settings.
"""

from pathlib import Path

import pandas as pd


def add_flags(df, object_min_coverage, allow_upsampling):
    df = df.copy()
    ok = df["status"] == "ok"
    df["low_coverage"] = ok & (df["coverage_mean"] < object_min_coverage)
    df["upsampled"] = ok & (df["native_pix_per_output"] < 1.0)
    df["no_signal"] = ok & ~(df["vmax"] > df["vmin"])
    df["usable"] = ok & ~df["low_coverage"] & ~df["no_signal"]
    if not allow_upsampling:
        df["usable"] &= ~df["upsampled"]
    return df


def write(df, path):
    path = Path(path)
    df.to_parquet(path.with_suffix(".parquet"), index=False)
    df.to_csv(path.with_suffix(".csv"), index=False)


def read(run_dir):
    return pd.read_parquet(Path(run_dir) / "manifest.parquet")
