# Phase 1 data audit: LEMUR (observed) side

Audit of all 2,244 LEMUR images (2026-10-16) with `python -m domain_gap.audit_lemur`
(per-object table `outputs/audit/lemur_audit.csv`, summary
`outputs/audit/lemur_audit_summary.json`). Cosmology: Planck 2018. Physical fields of view
are square boxes 250 or 500 kpc on a side, centred on the catalog's X-ray centre. The
simulated side is covered in `docs/tng_mock_provenance.md` and the regeneration plan below.

## 1. What a LEMUR image is

| Property | LEMUR |
|---|---|
| Sample | 1,302 clusters (an ObsID in the CDA "clusters of galaxies" category) and 942 galaxies |
| Pixel scale and projection | 0.492" (native ACIS pixels), RA---TAN / DEC--TAN, ICRS |
| Image size | the whole merged field, 21–40' across (5–95% of clusters) |
| Pixel values | F = (C − B) / E: photons cm⁻² s⁻¹ per pixel (`BUNIT = /cm**2 /s`) |
| Bands | broad 0.5–7 keV; soft 0.5–2 keV; hard 2–7 keV |
| Exposure map E | cm² s, monochromatic at 2.3 keV (broad), 1.25 keV (soft), 3.8 keV (hard) |
| Background | subtracted in every image (`BKGSUB = T`): ACIS blank-sky events, reprojected, scaled per chip to the 9–12 keV particle background |
| Normalization or clipping | none; pixel values are physical |
| Also available | counts C and background B for every band, broad exposure map, ObsID list, clean exposure, X-ray centre and target position for every object |
| Not available | point-source masks, explicit validity masks (coverage is E > 0), PSF maps |

Two properties matter for any intensity normalization:

- **The images are dominated by empty pixels at native resolution.** In the 4.2' cutout
  around a cluster's X-ray centre, the median cluster has 83% of pixels exactly zero (no
  source count and no background event) and 89% of the remaining pixels negative.
- **B is a binned realization of blank-sky events, not a smooth model,** so its Poisson
  noise is part of F. Smoothing or binning has to come before any percentile-based
  scaling. The current AstroCLIP preprocessing does this: 3.9" grid, σ = 1.5 px.

No pixel is NaN. The current fixed-angle AstroCLIP cutout (512 native px, 4.2') is fully
inside the exposed area for the median cluster.

## 2. Metadata limits for physical fields of view and intensity

- **Redshift:** 1,184 of 1,302 clusters (91%) have one. The other 118 can only enter the
  fixed-angle control.
- **The redshift range is wide.** It spans 0.006–0.99 (5–95%), with a median of 0.167. The
  same physical field therefore covers very different numbers of native pixels:

| z | Clusters | ACIS-I only | Median exposure (ks) | 250 kpc (arcmin) | 250 kpc (native px) | 500 kpc (native px) | 500 kpc ≥95% exposed |
|---|---|---|---|---|---|---|---|
| ≤ 0.03 | 161 | 90 | 38 | 19.6 | 2,388 | 4,777 | 6 |
| 0.03–0.05 | 76 | 48 | 37 | 4.8 | 585 | 1,171 | 53 |
| 0.05–0.1 | 186 | 135 | 17 | 2.9 | 347 | 695 | 167 |
| 0.1–0.2 | 220 | 174 | 18 | 1.6 | 196 | 392 | 210 |
| 0.2–0.4 | 256 | 215 | 22 | 0.96 | 117 | 234 | 254 |
| 0.4–0.7 | 157 | 139 | 31 | 0.66 | 81 | 161 | 154 |
| > 0.7 | 128 | 63 | 48 | 0.52 | 63 | 126 | 124 |

  - At z ≲ 0.03 a 500 kpc field is larger than the ACIS field, so coverage fails.
  - At z ≳ 0.2 a 250 kpc field spans fewer native pixels than a 144 px output, so it would
    be upsampled.
  - Clusters that are ≥95% exposed and need no upsampling:

| Field | 144 px output | 252 px output |
|---|---|---|
| 250 kpc | 509 (z 0.005–0.21) | 309 (z 0.005–0.11) |
| 500 kpc | 829 (z 0.015–0.64) | 539 (z 0.015–0.25) |

- **Exposure:** clean exposure ranges from 5 to 193 ks (5–95%), with a median of 25 ks.
  The old mocks used a fixed 100 ks, so the noise levels differ systematically.
- **Instrument:** 966 clusters are ACIS-I only, 283 ACIS-S only and 53 mixed. The old mocks
  were ACIS-I only.
- **Merged observations:** 25% of clusters combine more than one ObsID, so their PSF and
  depth vary across the image.
- **Resolution:** the on-axis PSF (~0.5") is 0.06–4 kpc (5–95%; median 1.5 kpc). That is
  below the output pixel of a 250 kpc / 144 px image (1.7 kpc), except at high redshift.
- **Physical intensity:**
  - F is a photon flux under a monochromatic exposure map. It is comparable across LEMUR
    objects, and with simulations only if those go through the same exposure correction.
  - Comparing intensities across redshift also needs cosmological surface-brightness dimming
    and K-corrections. Comparing at matched redshift avoids both.

## 3. Proposed module structure and configuration

```
domain_gap/
  audit_lemur.py      Phase 1 (this report)
  io.py               read LEMUR products and regenerated mocks into one Image record
                      (F, C, B, E, WCS, z, centre, metadata)
  spatial.py          physical or angular field, recentre, area-weighted resample,
                      coverage mask and fraction
  intensity.py        morphology mode (smooth, percentile clip, asinh on covered pixels)
                      and physical mode (one shared transform, parameters recorded)
  model_input.py      144 / 252 px, three-channel replication, saved arrays
  manifest.py         Parquet/CSV manifest with QC flags; resumable batches
  qa.py               comparison figures
  embed.py            frozen AstroCLIP embeddings (reusing scripts/astroclip_xray_similarity.py)
  mocks/              pyXSIM + SOXS regeneration of the TNG mocks
configs/              baseline.yaml, harmonized_morphology.yaml, harmonized_physical.yaml
tests/                spatial, intensity, masks, metadata
```

Each YAML file fixes the field (kpc or arcmin), output size, smoothing scale, intensity
mode and its parameters, cosmology, band, and the coverage threshold below which an object
is flagged.

## 4. Recommendations for normalization

- **Smooth or bin to the output grid first, then normalize.** At native resolution most
  LEMUR pixels are exactly zero or negative, so percentiles of raw pixels are meaningless.
- **Morphology mode:**
  1. Area-weighted resample to the physical grid and smooth by a fixed physical scale.
  2. Clip at 0, then percentile-clip and asinh-stretch using covered pixels only.
  3. Write uncovered pixels as a separate mask channel or flag, not as zero emission.
- **Physical mode:**
  - Convert F to surface brightness per physical area at the source and apply one fixed
    transform to all images, e.g. asinh with a global scale from the pooled LEMUR and mock
    distribution. Record the scale.
  - Compare at matched redshift rather than correcting for dimming. That is a strong
    reason to simulate the mocks at LEMUR-like redshifts.
- **Keep observing conditions out of the comparison where possible:** match the mocks'
  exposure, instrument and redshift to the LEMUR clusters they are compared with, rather
  than one 100 ks, z = 0.05 configuration.

## 5. Regenerating the TNG mocks (decided 2026-10-16)

Regenerate from public TNG data, following the spec: mocks stop at physical products, and
everything else happens in the shared pipeline.

- **Halos:** the 280 TNG300 and 352 TNG-Cluster halos of the `CCcriteria.hdf5` catalogs at
  snapshot 99 (the student's selection). Keep the cooling-time labels; record the old
  exclusions (merger halos, etc.) as flags rather than dropping halos.
- **Emission:** pyXSIM APEC from hot, non-star-forming gas within 3 Mpc. Use an explicit
  TNG cosmology (h = 0.6774), unwrap halos across the box edge, and set random seeds.
- **Observation:** SOXS `chandra_acisi_cy0` with the default 8" dither. Redshifts and
  exposures come from a grid matched to the LEMUR sample. Optionally simulate ACIS-S as well.
- **Products per halo, projection, redshift and exposure:**
  - the event file and counts image at 0.492";
  - an exposure map;
  - a separately simulated background-only event file, binned and subtracted like LEMUR's B,
    so that F = (C − B) / E has the same meaning;
  - the soft and hard bands as for LEMUR.
- **Decided (2026-10-16, Carter):** redshifts 0.05, 0.1 and 0.2; exposures 20 and 100 ks;
  ACIS-I only to start. That is 632 halos × 3 projections × 6 settings. The TNG API key
  will be read from `~/.config/tng_api_key` (never committed).
- **Needed from Carter:**
  - a TNG account API key, for gas cutouts of the eight fields used;
  - the choices of redshift grid, exposure strategy and whether to include ACIS-S.
- **Rough data volume:** ~30–50 GB of gas cutouts for TNG300 and ~0.1–0.2 TB for
  TNG-Cluster, plus photon lists (an estimate, to be refined with the first halos).
