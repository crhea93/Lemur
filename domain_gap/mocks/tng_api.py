"""Minimal client for the IllustrisTNG web API (https://www.tng-project.org/data/docs/api/).

The API key is read from the TNG_API_KEY environment variable or from
~/.config/tng_api_key, and is never written anywhere else.
"""

import os
import time
from pathlib import Path

import requests

BASE_URL = "https://www.tng-project.org/api"
KEY_FILE = Path.home() / ".config" / "tng_api_key"
# Gas fields the emission model needs (velocities for pyXSIM's Doppler shifts).
GAS_FIELDS = (
    "Coordinates",
    "Velocities",
    "Density",
    "Masses",
    "InternalEnergy",
    "ElectronAbundance",
    "GFM_Metallicity",
    "StarFormationRate",
    "GFM_CoolingRate",
)


def api_key():
    key = os.environ.get("TNG_API_KEY")
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text().strip()
    if not key:
        raise RuntimeError(f"No TNG API key: set TNG_API_KEY or write it to {KEY_FILE}")
    return key


def get(url, params=None, stream=False, tries=8):
    """GET with the API key, retrying transient failures.

    The data servers return 503 now and then under load, so the waits grow
    from 15 s to 5 min (about 18 min in all).
    """
    for attempt in range(tries):
        try:
            response = requests.get(
                url,
                params=params,
                headers={"api-key": api_key()},
                stream=stream,
                timeout=120,
            )
            if response.status_code >= 500 and attempt + 1 < tries:
                raise requests.HTTPError(f"{response.status_code} from {url}")
            response.raise_for_status()
            return response
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if attempt + 1 == tries:
                raise
            time.sleep(min(15 * 2**attempt, 300))


def halo_url(sim, snapshot, halo_id):
    return f"{BASE_URL}/{sim}/snapshots/{snapshot}/halos/{halo_id}/"


def halo_info(sim, snapshot, halo_id):
    """The group-catalog entry of one FoF halo (GroupPos, Group_M_Crit500, ...)."""
    return get(halo_url(sim, snapshot, halo_id) + "info.json").json()


def simulation_info(sim):
    """Simulation metadata (box size, cosmology, ...)."""
    return get(f"{BASE_URL}/{sim}/").json()


def download_gas_cutout(sim, snapshot, halo_id, path, fields=GAS_FIELDS, split=False):
    """Download the FoF gas of one halo to ``path`` (skipped if already complete).

    ``split`` downloads the fields in groups and merges them: the servers fail
    (503) to build single cutouts of the largest halos (> ~40M gas cells).
    """
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    if split:
        return _download_split(sim, snapshot, halo_id, path)
    partial = path.with_suffix(path.suffix + ".part")
    response = get(
        halo_url(sim, snapshot, halo_id) + "cutout.hdf5",
        params={"gas": ",".join(fields)},
        stream=True,
    )
    with open(partial, "wb") as handle:
        for chunk in response.iter_content(chunk_size=1 << 22):
            handle.write(chunk)
    partial.rename(path)
    return path


# Field groups of a split download. Each has Masses, to check that the parts
# list the cells in the same order.
SPLIT_GROUPS = (
    ("Coordinates", "Masses"),
    ("Velocities", "Density", "Masses"),
    (
        "InternalEnergy",
        "ElectronAbundance",
        "GFM_Metallicity",
        "StarFormationRate",
        "GFM_CoolingRate",
        "Masses",
    ),
)


def _download_split(sim, snapshot, halo_id, path):
    import h5py
    import numpy as np

    parts = []
    for i, group in enumerate(SPLIT_GROUPS):
        part = path.with_name(f"{path.stem}.part{i}{path.suffix}")
        download_gas_cutout(sim, snapshot, halo_id, part, fields=group)
        parts.append(part)
    merged = path.with_suffix(path.suffix + ".merge")
    with h5py.File(merged, "w") as out:
        gas = out.create_group("PartType0")
        masses = None
        for part in parts:
            with h5py.File(part, "r") as f:
                if "Header" in f and "Header" not in out:
                    f.copy("Header", out)
                m = f["PartType0"]["Masses"][...]
                if masses is None:
                    masses = m
                elif not np.array_equal(m, masses):
                    raise ValueError(f"cutout parts of halo {halo_id} list different cells")
                for key in f["PartType0"]:
                    if key not in gas:
                        f.copy(f["PartType0"][key], gas, name=key)
    merged.rename(path)
    for part in parts:
        part.unlink()
    return path
