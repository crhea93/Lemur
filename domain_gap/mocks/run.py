"""Generate the Chandra mocks of TNG halos described in a YAML config.

For every simulation, halo, redshift, projection and exposure:

    {output_root}/{sim}/{halo}/z{z}/{proj}/{exp}ks/
        {band}_counts.fits.gz, {band}_flux.fits.gz   (band = broad, soft, hard)
        events.fits.gz                               (if keep_events)
        meta.json                                    (settings, seeds, numbers)

plus {output_root}/reference/ with the shared background and exposure maps.
Finished observations are skipped, so an interrupted run can be restarted.

    python -m domain_gap.mocks.run --config configs/mocks.yaml [--sim TNG300-1] [--halos 0 1]
    python -m domain_gap.mocks.run --config configs/mocks.yaml --synthetic   # no TNG data needed

With workers > 1 (config or --workers) every halo runs in its own process and
logs to {output_root}/logs/{sim}_{halo}.log.

The reference background includes the faint CXB (observe.make_cxb_reference).
Observations made before it was added are brought up to date, without
re-simulating, by

    python -m domain_gap.mocks.run --config configs/mocks.yaml --refit
"""

import argparse
import csv
import gzip
import json
import shutil
import subprocess
import sys
import time
import zlib
from pathlib import Path

import yaml

from . import emission, gas, observe, tng_api

ROOT = Path(__file__).resolve().parents[2]
BANDS = tuple(observe.BANDS)


def seed(*parts):
    """Stable 31-bit seed from the identifiers of a step."""
    return zlib.crc32("|".join(str(p) for p in parts).encode()) & 0x7FFFFFFF


def obs_dir(root, sim, halo, z, proj, exp):
    return Path(root) / sim / str(halo) / f"z{z:.2f}" / proj / f"{exp:g}ks"


def is_done(directory):
    return (directory / "meta.json").exists() and all(
        (directory / f"{band}_flux.fits.gz").exists() for band in BANDS
    )


def read_halos(path):
    with open(ROOT / path) as handle:
        return [int(row["halo_id"]) for row in csv.DictReader(handle)]


def prepare_halo(cfg, sim, halo, work, synthetic):
    """Local halo file (centred, unwrapped) and catalog metadata."""
    halo_file = work / "halo_local.hdf5"
    if synthetic:
        gas.synthetic_cluster(halo_file, seed=seed(sim, halo, "synthetic"))
        return halo_file, {"synthetic": True}
    info = tng_api.halo_info(sim, cfg["snapshot"], halo)
    box = tng_api.simulation_info(sim)["boxsize"]
    cutout = tng_api.download_gas_cutout(
        sim, cfg["snapshot"], halo, work / "cutout.hdf5"
    )
    # The potential minimum of the FoF group (ckpc/h), as GroupPos or pos_x/y/z.
    center = info.get("GroupPos") or [info["pos_x"], info["pos_y"], info["pos_z"]]
    gas.write_local_halo(
        halo_file, gas.read_cutout(cutout), center=center, box_size=box
    )
    if not cfg.get("keep_cutouts"):
        cutout.unlink()
    keys = (
        "mass_crit500",
        "r_crit500",
        "mass",
        "pos_x",
        "pos_y",
        "pos_z",
        "GroupPos",
        "Group_M_Crit500",
        "Group_R_Crit500",
    )
    return halo_file, {k: info[k] for k in keys if k in info}


def pending(cfg, sim, halo):
    """The (redshift, projection, exposure) observations of a halo still to make."""
    root = Path(cfg["output_root"])
    return [
        (z, proj, exp)
        for z in cfg["redshifts"]
        for proj in cfg["projections"]
        for exp in cfg["exposures_ks"]
        if not is_done(obs_dir(root, sim, halo, z, proj, exp))
    ]


def run_halo(cfg, sim, halo, reference, synthetic=False):
    todo = pending(cfg, sim, halo)
    if not todo:
        return 0
    # Intermediate files (cutout, local halo, photon and event lists) go to
    # work_root, ideally a fast disk; only the products go to output_root.
    work_root = cfg.get("work_root") or Path(cfg["output_root"]) / "work"
    work = Path(work_root) / f"{sim}_{halo}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        return _run_halo(cfg, sim, halo, reference, synthetic, todo, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run_halo(cfg, sim, halo, reference, synthetic, todo, work):
    root = Path(cfg["output_root"])
    started = time.time()
    halo_file, halo_meta = prepare_halo(cfg, sim, halo, work, synthetic)
    for z in sorted({z for z, _, _ in todo}):
        photons = work / f"photons_z{z:.2f}"
        n_photons = emission.make_photon_list(
            halo_file,
            photons,
            z,
            cfg["photon_area_cm2"],
            cfg["photon_exposure_ks"],
            seed(sim, halo, z, "photons"),
        )
        for proj in sorted({p for zz, p, _ in todo if zz == z}):
            events = work / f"events_z{z:.2f}_{proj}"
            simput = emission.project(
                photons,
                events,
                proj,
                cfg["sky_center_deg"],
                seed(sim, halo, z, proj, "project"),
            )
            for exp in [e for zz, p, e in todo if zz == z and p == proj]:
                out = obs_dir(root, sim, halo, z, proj, exp)
                out.mkdir(parents=True, exist_ok=True)
                obs_seed = seed(sim, halo, z, proj, exp, "observe")
                evt = observe.simulate_observation(
                    simput, work / "obs_evt.fits", exp, cfg["sky_center_deg"], obs_seed
                )
                header_meta = {
                    "SIM": sim,
                    "HALOID": halo,
                    "PROJ": proj,
                    "REDSHIFT": z,
                    "OBJECT": f"{sim}_{halo}_{proj}",
                }
                summary = observe.make_products(evt, reference, out, header_meta)
                if cfg.get("keep_events"):
                    with (
                        open(evt, "rb") as src,
                        gzip.open(out / "events.fits.gz", "wb", 6) as dst,
                    ):
                        shutil.copyfileobj(src, dst)
                evt.unlink()
                meta = {
                    "sim": sim,
                    "halo_id": halo,
                    "redshift": z,
                    "projection": proj,
                    "exposure_ks": exp,
                    "photons_drawn": n_photons,
                    "seeds": {
                        "photons": seed(sim, halo, z, "photons"),
                        "project": seed(sim, halo, z, proj, "project"),
                        "observe": obs_seed,
                    },
                    "settings": {
                        k: cfg[k]
                        for k in (
                            "photon_area_cm2",
                            "photon_exposure_ks",
                            "sky_center_deg",
                            "snapshot",
                        )
                    },
                    "emission": {
                        "model": "apec",
                        "band_keV": [emission.EMIN_KEV, emission.EMAX_KEV],
                        "nH_1e22": emission.NH_1E22,
                        "radius_Mpc": emission.RADIUS_MPC,
                    },
                    "halo": halo_meta,
                    "products": summary,
                }
                (out / "meta.json").write_text(json.dumps(meta, indent=1, default=str))
            for f in work.glob(f"events_z{z:.2f}_{proj}*"):
                f.unlink()
        for f in work.glob(f"photons_z{z:.2f}*"):
            f.unlink()
    print(
        f"  {sim} {halo}: {len(todo)} observations in {time.time() - started:.0f} s",
        flush=True,
    )
    return len(todo)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", default=str(ROOT / "configs" / "mocks.yaml"))
    parser.add_argument("--sim", help="Only this simulation")
    parser.add_argument("--halos", nargs="*", type=int, help="Only these halo IDs")
    parser.add_argument(
        "--limit", type=int, help="Only the first N halos of each simulation"
    )
    parser.add_argument(
        "--synthetic", action="store_true", help="Use synthetic clusters (tests)"
    )
    parser.add_argument("--output-root", help="Override output_root")
    parser.add_argument(
        "--workers",
        type=int,
        help="Halos at once, each in its own process (default: config 'workers', else 1)",
    )
    parser.add_argument(
        "--refit",
        action="store_true",
        help="Only recompute flux images made with an older reference background",
    )
    args = parser.parse_args(argv)

    cfg = yaml.safe_load(open(args.config))
    if args.output_root:
        cfg["output_root"] = args.output_root
    reference = Path(cfg["output_root"]) / "reference"
    observe.make_reference(reference, cfg["sky_center_deg"], seed("reference"))
    observe.make_cxb_reference(reference, cfg["sky_center_deg"], seed("reference", "cxb"))
    if args.refit:
        return refit_all(cfg, reference)
    jobs = []
    for sim_cfg in cfg["simulations"]:
        sim = sim_cfg["name"]
        if args.sim and sim != args.sim:
            continue
        halos = args.halos or read_halos(sim_cfg["halos"])
        if args.limit:
            halos = halos[: args.limit]
        jobs += [(sim, halo) for halo in halos if pending(cfg, sim, halo)]
    workers = args.workers or cfg.get("workers", 1)
    if workers > 1 and len(jobs) > 1:
        return run_parallel(args, cfg, jobs, workers)
    total = failed = 0
    for sim, halo in jobs:
        try:
            total += run_halo(cfg, sim, halo, reference, synthetic=args.synthetic)
        except Exception as exc:  # keep going; the halo is retried next run
            failed += 1
            print(f"  {sim} {halo}: FAILED {type(exc).__name__}: {exc}", flush=True)
    print(f"Made {total} observations.")
    return 1 if failed else 0


def refit_all(cfg, reference):
    """Bring every finished observation up to the current reference background."""
    root = Path(cfg["output_root"])
    done = [m.parent for m in sorted(root.glob("*/*/z*/*/*ks/meta.json"))]
    changed = sum(observe.refit_flux(obs, reference) for obs in done if is_done(obs))
    print(f"Refitted {changed} of {len(done)} observations.", flush=True)
    return 0


def run_parallel(args, cfg, jobs, workers):
    """Run each halo as ``run --halos H --workers 1`` in its own process.

    A halo that crashes or is killed (e.g. for memory) loses only itself; its
    log is {output_root}/logs/{sim}_{halo}.log and a rerun retries it.
    """
    logs = Path(cfg["output_root"]) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    base = [sys.executable, "-m", "domain_gap.mocks.run", "--config", args.config]
    base += ["--workers", "1"]
    if args.output_root:
        base += ["--output-root", args.output_root]
    if args.synthetic:
        base.append("--synthetic")
    print(f"{len(jobs)} halos to do, {workers} at once.", flush=True)
    queue, running, n_done, failed = list(jobs), {}, 0, []
    while queue or running:
        while queue and len(running) < workers:
            sim, halo = queue.pop(0)
            log = open(logs / f"{sim}_{halo}.log", "w")
            proc = subprocess.Popen(
                base + ["--sim", sim, "--halos", str(halo)],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
            running[proc] = (sim, halo, log, time.time())
        time.sleep(5)
        for proc in [p for p in running if p.poll() is not None]:
            sim, halo, log, started = running.pop(proc)
            log.close()
            n_done += 1
            status = "ok" if proc.returncode == 0 else f"FAILED (exit {proc.returncode})"
            if proc.returncode != 0:
                failed.append((sim, halo))
            print(
                f"[{n_done}/{len(jobs)}] {sim} {halo}: {status} "
                f"in {time.time() - started:.0f} s",
                flush=True,
            )
    print(f"Finished {len(jobs) - len(failed)} of {len(jobs)} halos.", flush=True)
    if failed:
        print("Failed (rerun to retry): " + " ".join(f"{s}:{h}" for s, h in failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
