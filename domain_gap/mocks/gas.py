"""Halo gas in a form yt (and so pyXSIM) can read.

A TNG FoF cutout holds gas cells in periodic comoving box coordinates. We shift
them so the halo centre (the group's potential minimum, GroupPos) sits at the
middle of a non-periodic local box, unwrapping cells that straddle the box edge,
and write a minimal Arepo-style HDF5 file in TNG code units (ckpc/h,
1e10 Msun/h, km/s). The original student mocks skipped the unwrapping, which
truncated halos at the box edge.

``synthetic_cluster`` writes a file of the same form for an isothermal beta
model, so the whole mock chain can be tested without TNG data.
"""

from pathlib import Path

import h5py
import numpy as np

# TNG cosmology (Planck 2015).
TNG_H = 0.6774
TNG_OMEGA_M = 0.3089
TNG_OMEGA_L = 0.6911
PROTON_MASS_G = 1.67262192e-24
KPC_CM = 3.0856775814913673e21
MSUN_G = 1.98841e33
X_H = 0.76
BOLTZMANN_ERG = 1.380649e-16
KEV_ERG = 1.602176634e-9


def unwrap(coordinates, center, box_size):
    """Coordinates relative to ``center`` under the periodic box (minimum image)."""
    delta = np.asarray(coordinates, dtype=np.float64) - np.asarray(
        center, dtype=np.float64
    )
    return delta - box_size * np.round(delta / box_size)


def write_local_halo(out_path, gas, center, box_size, scale_factor=1.0):
    """Write ``gas`` (dict of TNG gas fields) centred on ``center`` to ``out_path``.

    Returns the side of the local box in code units (ckpc/h).
    """
    rel = unwrap(gas["Coordinates"], center, box_size)
    half = float(np.abs(rel).max()) * 1.01 + 1.0
    local = rel + half  # halo centre at (half, half, half)
    n = len(local)
    with h5py.File(out_path, "w") as f:
        header = f.create_group("Header")
        header.attrs.update(
            {
                "NumPart_ThisFile": np.array([n, 0, 0, 0, 0, 0], dtype=np.int32),
                "NumPart_Total": np.array([n, 0, 0, 0, 0, 0], dtype=np.uint32),
                "NumPart_Total_HighWord": np.zeros(6, dtype=np.uint32),
                "MassTable": np.zeros(6),
                "Time": scale_factor,
                "Redshift": 1.0 / scale_factor - 1.0,
                "BoxSize": 2 * half,
                "NumFilesPerSnapshot": 1,
                "Omega0": TNG_OMEGA_M,
                "OmegaLambda": TNG_OMEGA_L,
                "HubbleParam": TNG_H,
                "Flag_Sfr": 1,
                "Flag_Cooling": 1,
                "Flag_Metals": 1,
                "Flag_Feedback": 1,
                "Flag_DoublePrecision": 1,
            }
        )
        f.create_group("Config").attrs["VORONOI"] = 1
        part = f.create_group("PartType0")
        part["Coordinates"] = local
        part["ParticleIDs"] = np.arange(n, dtype=np.uint64)
        for field in (
            "Velocities",
            "Density",
            "Masses",
            "InternalEnergy",
            "ElectronAbundance",
            "GFM_Metallicity",
            "StarFormationRate",
            "GFM_CoolingRate",
        ):
            part[field] = np.asarray(gas[field])
    return 2 * half


def read_cutout(path):
    """Gas fields of a TNG API cutout file."""
    with h5py.File(path, "r") as f:
        return {key: f["PartType0"][key][...] for key in f["PartType0"]}


def synthetic_cluster(
    out_path,
    n_cells=200_000,
    kT_keV=5.0,
    n0_cm3=5e-3,
    r_core_kpc=150.0,
    beta=0.66,
    r_max_kpc=2000.0,
    metallicity=0.0042,
    seed=1,
):
    """Isothermal beta-model gas cloud written like ``write_local_halo`` output.

    Cells are equal-mass samples of the gas density profile, so each cell's
    volume is mass / density, as for Voronoi cells.
    """
    rng = np.random.default_rng(seed)
    # Sample radii with probability proportional to n(r) r^2.
    r_grid = np.linspace(1.0, r_max_kpc, 20000)
    density = n0_cm3 * (1 + (r_grid / r_core_kpc) ** 2) ** (-1.5 * beta)
    cdf = np.cumsum(density * r_grid**2)
    cdf /= cdf[-1]
    r = np.interp(rng.random(n_cells), cdf, r_grid)
    direction = rng.normal(size=(n_cells, 3))
    direction /= np.linalg.norm(direction, axis=1)[:, None]
    pos_kpc = direction * r[:, None]

    n_e = n0_cm3 * (1 + (r / r_core_kpc) ** 2) ** (-1.5 * beta)
    mu_e = 2.0 / (1.0 + X_H)
    rho_cgs = n_e * mu_e * PROTON_MASS_G
    shell = (
        4
        * np.pi
        * np.trapezoid(
            n0_cm3 * (1 + (r_grid / r_core_kpc) ** 2) ** (-1.5 * beta) * r_grid**2,
            r_grid,
        )
    )
    total_mass_g = shell * mu_e * PROTON_MASS_G * KPC_CM**3
    cell_mass_g = total_mass_g / n_cells

    # TNG code units at a = 1: ckpc/h, 1e10 Msun/h, (km/s)^2.
    length_unit = KPC_CM / TNG_H
    mass_unit = 1e10 * MSUN_G / TNG_H
    electron_abundance = np.full(n_cells, (1 + X_H) / (2 * X_H))  # fully ionized: ne/nH
    mu = 4.0 / (1 + 3 * X_H + 4 * X_H * electron_abundance)
    temperature_k = kT_keV * KEV_ERG / BOLTZMANN_ERG
    u_cgs = temperature_k * BOLTZMANN_ERG / ((5.0 / 3.0 - 1) * mu * PROTON_MASS_G)
    gas = {
        "Coordinates": pos_kpc * TNG_H,
        "Velocities": np.zeros((n_cells, 3)),
        "Density": rho_cgs / (mass_unit / length_unit**3),
        "Masses": np.full(n_cells, cell_mass_g / mass_unit),
        "InternalEnergy": np.full(n_cells, u_cgs / 1e10),
        "ElectronAbundance": electron_abundance,
        "GFM_Metallicity": np.full(n_cells, metallicity),
        "StarFormationRate": np.zeros(n_cells),
        "GFM_CoolingRate": np.full(n_cells, -1e-30),
    }
    write_local_halo(out_path, gas, center=np.zeros(3), box_size=1e9)
    return Path(out_path)
