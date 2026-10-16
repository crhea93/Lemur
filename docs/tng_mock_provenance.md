# How the original TNG Chandra mocks were made

Reconstructed from the student's recovered code in `/home/crhea/friend-mac-recovery/`
(read 2026-10-16; no FITS files survive there, only code, notebooks, PNGs, embeddings
and tables). File references are relative to that folder.

## Missing pieces

- **No mock FITS survive.** The SOXS products were written on MPCDF Vera
  (`/vera/ptmp/gc/reka/masters/clusters_300/cluster_{id}/`) and the processed FITS on an
  external drive (`/Volumes/LaCie/masters/tng_300_mocks_cleaned/`,
  `.../tng_cluster_mocks_cleaned/`).
- **The step from SOXS image to `*_cleaned_binned_normalized.fits` is not in the
  recovery.** Inferred from the products: 2440 → 610 px suggests 4×4 binning (1.968"/px);
  values are min–max normalized to [0, 1] with no visible background or point sources.

## Generator: `masters/debugging_centering/Pipeline_clean.py`

(`Pipeline_clean-Copy1.py` is a TNG-Cluster re-run of 134 halos.)

| Step | Setting |
|---|---|
| Snapshot | 99 (z = 0) for both simulations |
| TNG300 halos | the 280 FoF IDs of the TNG300 `CCcriteria.hdf5` (listed in the comment on line 32) |
| TNG-Cluster halos | the 352 IDs of the TNG-Cluster `CCcriteria.hdf5` (a copy is in `masters/CCcriteria.hdf5`) |
| Gas data | `illustris_python` `loadHalo(..., partType='gas')` on local `/virgotng` data (FoF gas only) |
| Gas used | `StarFormationRate == 0` and `GFM_CoolingRate < 0`; no temperature or density cut |
| Centre | iterative smoothed 3D density-histogram peak (`masters/my_helper_functions.py:63-125`) |
| Region | sphere of 3 Mpc around the centre |
| Emission | `pyxsim.CIESourceModel("apec", 0.5, 7.0, 3000, metallicity from GFM_Metallicity)`, other settings default |
| Photons | redshift 0.05, area 1000 cm², exposure 1000 ks; cosmology from the snapshot (TNG Planck15) |
| Projection | x, y and z; sky centre (45°, 30°); `tbabs` with nH = 4×10²⁰ cm⁻² |
| Instrument | `soxs.instrument_simulator(..., (100.0, "ks"), "chandra_acisi_cy0", ...)` with instrumental, foreground and point-source backgrounds on; dither 256" (SOXS default 8"); roll 0 |
| Image | `soxs.write_image(evt, img, emin=0.5, emax=2.0)` at native pixels; no exposure correction |
| Labels | `centralCoolingTime[:, 99]` (Gyr) from `CCcriteria.hdf5`; models use its natural log |

No random seed is set anywhere, so the original mocks are not bit-reproducible.

## Known problems in the original generator

- Halos that straddle the periodic box edge are not unwrapped (`handle_box_edges` is a
  no-op and uses the TNG300 box size for TNG-Cluster too); e.g. halo 11's y projection
  is visibly truncated.
- h = 0.68 is hard-coded in the centring (TNG uses 0.6774), and the centring's ±3σ cut
  mixes units.
- Dither of 256" smears the chip gaps and tapers exposure beyond ~8', and no exposure
  map is made or applied.

## Downstream image preparation (differs between the two samples)

- **TNG300:** central 252×252 crop of the 610×610 normalized image, re-normalized within
  the crop, saved as **greyscale** PNG (`MSC_LATEST/code_cluster.ipynb` cell 21).
- **TNG-Cluster:** 610×610 normalized image saved with **viridis**, then center-cropped to
  252×252 without re-normalization (`code_cluster.ipynb` cells 14–15).
- AstroCLIP input: the PNG converted to RGB and `ToTensor()` only.

## Selections used for the final embeddings

| Sample | Halos with mocks | Excluded | Final |
|---|---|---|---|
| TNG300 | 253 of 280 | 14 + halo 172 (`code_cluster.ipynb` cell 25; `pipeline_tng300.ipynb` cell 13) | 238 halos, 714 images |
| TNG-Cluster | 338 of 352 | 7 "merger" halos (`code_cluster.ipynb` cells 9–15) | 331 halos, 992 images embedded |

## Software the student used (Mac, July 2024)

Python 3.12.3, pyxsim 4.4.0, soxs 4.8.5, yt 4.3.1, astropy 6.1.1, numpy 1.26.4.
AstroCLIP embeddings: Python 3.9.18, `astroclip.ckpt`.
