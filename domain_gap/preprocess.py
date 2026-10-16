"""Preprocess LEMUR and the TNG mocks identically for AstroCLIP (Phase 2).

    python -m domain_gap.preprocess --config configs/harmonized_morphology.yaml
        [--sources LEMUR TNG300-1 TNG-Cluster] [--limit N] [--workers 6]

Stage 1 (reads the FITS images; cached per image in
<data drive>/_domain_gap/preprocessed/_stage1/{spatial hash}/{source}/, shared
by configs that differ only in stage 2): the field's
surface brightness and coverage on the output grid (``spatial.extract``).
Stage 2: pixel mask, smoothing and intensity transform, written as

    inputs_{source}.npy   float32 (N, grid, grid) in [0, 1], the model inputs
    masks_{source}.npy    uint8, 1 where the output pixel is covered
    manifest.parquet/csv  one row per image (see domain_gap.manifest)
    run.json              config, fitted parameters, code version, counts

Stage 1 is resumable (finished images are skipped), so a run can be repeated
as more mocks finish; stage 2 is cheap and always redone.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import intensity, io, manifest, spatial

ROOT = io.ROOT
PREPROCESSED = io.DEFAULT_DATA / "_domain_gap" / "preprocessed"
SPATIAL_KEYS = ("band", "field", "grid", "cosmology", "center", "weighting")


def load_config(path):
    cfg = yaml.safe_load(open(path))
    cfg.setdefault("name", Path(path).stem)
    cfg.setdefault("output_dir", str(PREPROCESSED / cfg["name"]))
    return cfg


def spatial_hash(cfg):
    key = json.dumps({k: cfg.get(k) for k in SPATIAL_KEYS}, sort_keys=True)
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9_.+-]", "_", str(name))


def _jsonable(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, float) and np.isnan(value):
        return None
    return value


# ---------------------------------------------------------------- items


def list_items(cfg, sources=None, limit=None):
    """{source: [(kind, payload, name)]} in a fixed order."""
    items = {}
    lemur_cfg = cfg.get("lemur", {})
    if not sources or io.LEMUR in sources:
        catalog = io.lemur_catalog(
            lemur_cfg.get("db", io.DEFAULT_DB), lemur_cfg.get("clusters_only", True)
        )
        rows = [
            ("lemur", {k: _jsonable(v) for k, v in row.items()}, row["Name"])
            for row in catalog.to_dict("records")
        ]
        items[io.LEMUR] = rows[:limit] if limit else rows
    mock_cfg = cfg.get("mocks", {})
    for sim in mock_cfg.get("sims", []):
        if sources and sim not in sources:
            continue
        dirs = io.mock_observations(
            mock_cfg.get("root", io.DEFAULT_MOCKS),
            sims=[sim],
            redshifts=mock_cfg.get("redshifts"),
            exposures=mock_cfg.get("exposures_ks"),
            projections=mock_cfg.get("projections"),
        )
        rows = [("mock", str(d), io.mock_name(d)[1]) for d in dirs]
        items[sim] = rows[:limit] if limit else rows
    return items


# ---------------------------------------------------------------- stage 1


def _extract(img, center, method, cfg, info):
    info.update(
        redshift=img.redshift,
        exposure_ks=img.exposure_ks,
        center_ra=center[0],
        center_dec=center[1],
        center_method=method,
        image_pixel_arcsec=img.pixel_arcsec,
        **{k: _jsonable(v) for k, v in img.meta.items()},
    )
    cosmo = spatial.cosmology(cfg.get("cosmology", "Planck15"))
    side = spatial.field_side_arcsec(cfg["field"], img.redshift, cosmo)
    if side is None:
        info["status"] = "no redshift"
        return info, None, None
    grid = int(cfg["grid"])
    cx, cy = img.wcs.wcs_world2pix([center], 0)[0]
    sb, cov = spatial.extract(
        img.flux,
        img.weight,
        (float(cx), float(cy)),
        side / img.pixel_arcsec,
        grid,
        img.pixel_arcsec,
        weighted=cfg.get("weighting", "exposure") == "exposure",
    )
    q = grid // 4
    info.update(
        status="ok",
        field_arcsec=side,
        field_kpc=cfg["field"].get("kpc"),
        native_pix_per_output=side / spatial.ACIS_PIXEL_ARCSEC / grid,
        coverage_mean=float(cov.mean()),
        coverage_core=float(cov[q : grid - q, q : grid - q].mean()),
    )
    return info, sb, cov


def stage1_one(kind, payload, cfg):
    band = cfg["band"]
    if kind == "lemur":
        info = {"source": io.LEMUR, "name": payload["Name"], "band": band}
        img = io.load_lemur(payload, band, cfg.get("lemur", {}).get("data_dir", io.DEFAULT_DATA))
        if img is None:
            info["status"] = "missing files"
            return info, None, None
        if img.center_radec is None:
            info["status"] = "no center"
            return info, None, None
        return _extract(img, img.center_radec, payload.get("method") or "catalog", cfg, info)
    sim, name = io.mock_name(payload)
    info = {"source": sim, "name": name, "band": band}
    img = io.load_mock(payload, band)
    if cfg.get("center", "xray_peak") == "halo":
        return _extract(img, img.prior_radec, "halo", cfg, info)
    broad = img if band == "broad" else io.load_mock(payload, "broad")
    return _extract(img, io.peak_center(broad), "xray_peak", cfg, info)


def _stage1_task(args):
    kind, payload, name, cfg, path = args
    try:
        info, sb, cov = stage1_one(kind, payload, cfg)
    except Exception as exc:  # recorded, so one bad image does not stop the run
        source = io.LEMUR if kind == "lemur" else io.mock_name(payload)[0]
        info = {
            "source": source,
            "name": name,
            "band": cfg["band"],
            "status": f"error: {type(exc).__name__}: {exc}",
        }
        sb = cov = None
    arrays = {} if sb is None else {"sb": sb, "coverage": cov}
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, info=json.dumps(info, default=_jsonable), **arrays)
    tmp.rename(path)
    return info["status"]


def run_stage1(cfg, items, workers):
    # Shared by every config with the same spatial settings.
    base = Path(cfg.get("stage1_dir", PREPROCESSED / "_stage1"))
    base = base / spatial_hash(cfg)
    base.mkdir(parents=True, exist_ok=True)
    (base / "spatial.json").write_text(
        json.dumps({k: cfg.get(k) for k in SPATIAL_KEYS}, indent=1)
    )
    tasks, paths = [], {}
    for source, rows in items.items():
        (base / source).mkdir(exist_ok=True)
        paths[source] = []
        for kind, payload, name in rows:
            path = base / source / f"{safe_name(name)}.npz"
            paths[source].append(path)
            if not path.exists():
                tasks.append((kind, payload, name, cfg, path))
    print(f"Stage 1: {len(tasks)} images to extract ({base})", flush=True)
    started = time.time()
    if tasks:
        with ProcessPoolExecutor(workers) as pool:
            for n, _status in enumerate(pool.map(_stage1_task, tasks, chunksize=1), 1):
                if n % 200 == 0 or n == len(tasks):
                    print(f"  {n}/{len(tasks)} in {time.time() - started:.0f} s", flush=True)
    return paths


def load_stage1(paths):
    infos, sbs, covs = [], [], []
    for path in paths:
        with np.load(path) as data:
            infos.append(json.loads(str(data["info"])))
            sbs.append(data["sb"] if "sb" in data else None)
            covs.append(data["coverage"] if "coverage" in data else None)
    return infos, sbs, covs


# ---------------------------------------------------------------- stage 2


def smooth(sb, mask, cfg):
    s = cfg.get("smoothing", {})
    sigma = float(s.get("sigma_pix", 0.0))
    if s.get("masked", True):
        return spatial.masked_smooth(sb, mask, sigma)
    return spatial.zero_padded_smooth(sb, sigma)


def run_stage2(cfg, paths):
    out = Path(cfg["output_dir"])
    icfg = cfg.get("intensity", {"mode": "morphology"})
    pixel_min = float(cfg.get("coverage", {}).get("pixel_min", 0.5))
    a = float(icfg.get("asinh_a", 0.08))
    loaded = {}
    for source, source_paths in paths.items():
        infos, sbs, covs = load_stage1(source_paths)
        smoothed, masks = [], []
        for info, sb, cov in zip(infos, sbs, covs):
            if sb is None:
                smoothed.append(None)
                masks.append(None)
                continue
            mask = cov >= pixel_min if pixel_min > 0 else np.ones_like(cov, bool)
            smoothed.append(smooth(sb, mask, cfg))
            masks.append(mask)
        loaded[source] = (infos, smoothed, masks)

    params = {"mode": icfg["mode"], "asinh_a": a}
    if icfg["mode"] == "physical":
        params["dimming_exponent"] = icfg.get("dimming_exponent", 0)
        vmin, vmax = icfg.get("vmin"), icfg.get("vmax")
        if vmin is None or vmax is None:
            fit = icfg.get("fit", {})
            pool = [
                (img, m, info["redshift"], source)
                for source, (infos, imgs, ms) in loaded.items()
                for info, img, m in zip(infos, imgs, ms)
                if img is not None
                and info["coverage_mean"] >= cfg.get("coverage", {}).get("object_min", 0.95)
            ]
            fit_vmin, fit_vmax = intensity.fit_physical(
                [p[0] for p in pool],
                [p[1] for p in pool],
                [p[2] for p in pool],
                fit.get("lower_pct", 5.0),
                fit.get("upper_pct", 99.7),
                params["dimming_exponent"],
                groups=[p[3] for p in pool],
            )
            vmin = fit_vmin if vmin is None else vmin
            vmax = fit_vmax if vmax is None else vmax
            params["fitted_on"] = {s: sum(p[3] == s for p in pool) for s in loaded}
        params.update(vmin=float(vmin), vmax=float(vmax))

    rows = []
    counts = {}
    for source, (infos, imgs, ms) in loaded.items():
        inputs, masks = [], []
        for info, img, mask in zip(infos, imgs, ms):
            row = dict(info, index=-1, vmin=np.nan, vmax=np.nan)
            if img is not None:
                if icfg["mode"] == "physical":
                    values = intensity.physical(
                        img, mask, info["redshift"], params["vmin"], params["vmax"], a,
                        params["dimming_exponent"],
                    )
                    vmin, vmax = params["vmin"], params["vmax"]
                    if not (np.asarray(img)[mask] > vmin).any():
                        vmax = vmin  # nothing above the floor: flagged no_signal
                else:
                    values, vmin, vmax = intensity.morphology(
                        img, mask, icfg.get("lower_pct", 5.0), icfg.get("upper_pct", 99.7), a
                    )
                row.update(index=len(inputs), vmin=vmin, vmax=vmax)
                inputs.append(values)
                masks.append(mask.astype(np.uint8))
            rows.append(row)
        grid = int(cfg["grid"])
        np.save(out / f"inputs_{source}.npy", np.array(inputs, np.float32).reshape(-1, grid, grid))
        np.save(out / f"masks_{source}.npy", np.array(masks, np.uint8).reshape(-1, grid, grid))
        counts[source] = len(inputs)

    df = manifest.add_flags(
        pd.DataFrame(rows),
        cfg.get("coverage", {}).get("object_min", 0.95),
        cfg.get("allow_upsampling", True),
    )
    manifest.write(df, out / "manifest")
    commit = subprocess.run(
        ["git", "-C", str(ROOT), "describe", "--always", "--dirty"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    summary = {
        source: {
            "images": int((df["source"] == source).sum()),
            "ok": int(((df["source"] == source) & (df["status"] == "ok")).sum()),
            "usable": int(((df["source"] == source) & df["usable"]).sum()),
        }
        for source in loaded
    }
    run = {
        "config": cfg,
        "spatial_hash": spatial_hash(cfg),
        "intensity": params,
        "code_version": commit,
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": summary,
    }
    (out / "run.json").write_text(json.dumps(run, indent=1, default=_jsonable))
    return df, run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", required=True)
    parser.add_argument("--sources", nargs="*", help="LEMUR and/or simulation names")
    parser.add_argument("--limit", type=int, help="Only the first N images per source")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--output-dir", help="Override output_dir")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    if args.output_dir:
        cfg["output_dir"] = args.output_dir
    Path(cfg["output_dir"]).mkdir(parents=True, exist_ok=True)
    items = list_items(cfg, args.sources, args.limit)
    paths = run_stage1(cfg, items, args.workers)
    df, run = run_stage2(cfg, paths)
    for source, s in run["summary"].items():
        print(f"{source}: {s['images']} images, {s['ok']} extracted, {s['usable']} usable")
    print(f"Wrote {cfg['output_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
