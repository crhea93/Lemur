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


def download_gas_cutout(sim, snapshot, halo_id, path, fields=GAS_FIELDS):
    """Download the FoF gas of one halo to ``path`` (skipped if already complete)."""
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
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
