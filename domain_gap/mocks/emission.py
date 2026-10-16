"""X-ray photons from halo gas with pyXSIM.

Follows the original student mocks (hot, non-star-forming gas within 3 Mpc,
APEC 0.5-7 keV, 3000 bins, absorption by tbabs with nH = 4e20 cm^-2), with
the TNG cosmology passed explicitly and random seeds fixed.
"""

from pathlib import Path

from .gas import TNG_H, TNG_OMEGA_L, TNG_OMEGA_M

EMIN_KEV, EMAX_KEV, NBINS = 0.5, 7.0, 3000
RADIUS_MPC = 3.0
NH_1E22 = 0.04
ABSORB_MODEL = "tbabs"


def _hot_gas(pfilter, data):
    # As in the original mocks: no star formation and net cooling.
    return (data["PartType0", "StarFormationRate"] == 0.0) & (
        data["PartType0", "GFM_CoolingRate"] < 0.0
    )


def make_photon_list(halo_file, photon_prefix, redshift, area_cm2, exp_ks, seed):
    """Photons from the hot gas around the centre of ``halo_file`` at ``redshift``.

    Returns the number of photons. ``area_cm2`` must exceed the instrument's peak
    effective area and ``exp_ks`` the longest observation that will be drawn
    from these photons.
    """
    import pyxsim
    import yt
    from yt.utilities.cosmology import Cosmology

    yt.add_particle_filter(
        "hot_gas", function=_hot_gas, filtered_type="gas", requires=["density"]
    )
    ds = yt.load(str(halo_file))
    ds.add_particle_filter("hot_gas")
    sphere = ds.sphere(ds.domain_center, (RADIUS_MPC, "Mpc"))
    model = pyxsim.CIESourceModel(
        "apec",
        EMIN_KEV,
        EMAX_KEV,
        NBINS,
        ("hot_gas", "metallicity"),
        temperature_field=("hot_gas", "temperature"),
        emission_measure_field=("hot_gas", "emission_measure"),
        prng=seed,
    )
    cosmology = Cosmology(
        hubble_constant=TNG_H, omega_matter=TNG_OMEGA_M, omega_lambda=TNG_OMEGA_L
    )
    n_photons, _n_cells = pyxsim.make_photons(
        str(photon_prefix),
        sphere,
        redshift,
        (area_cm2, "cm**2"),
        (exp_ks, "ks"),
        model,
        center=ds.domain_center,
        cosmology=cosmology,
    )
    return int(n_photons)


def project(photon_prefix, event_prefix, axis, sky_center, seed):
    """Project the photons along ``axis`` and write a SIMPUT catalog for SOXS.

    Returns the SIMPUT file path.
    """
    import pyxsim

    pyxsim.project_photons(
        str(photon_prefix),
        str(event_prefix),
        axis,
        list(sky_center),
        absorb_model=ABSORB_MODEL,
        nH=NH_1E22,
        prng=seed,
    )
    events = pyxsim.EventList(f"{event_prefix}.h5")
    events.write_to_simput(str(event_prefix), overwrite=True)
    return Path(f"{event_prefix}_simput.fits")
