# Phase 2: shared preprocessing of LEMUR and the TNG mocks

LEMUR images and the regenerated mocks go through one code path, set by one YAML file.
Mocks stop at physical products (counts, background-subtracted flux, exposure); every
crop, resample, smoothing and normalization happens here.

## Running it

```
PY=~/miniconda3/envs/tng-mocks/bin/python            # preprocessing, QA
AC=~/miniconda3/envs/lemur-astroclip/bin/python      # embeddings
PYTHONPATH=. $PY -m domain_gap.preprocess --config configs/harmonized_morphology.yaml
PYTHONPATH=. $PY -m domain_gap.qa    --run <data drive>/_domain_gap/preprocessed/harmonized_morphology
PYTHONPATH=. $AC -m domain_gap.embed --run <data drive>/_domain_gap/preprocessed/harmonized_morphology
```

Options: `--sources LEMUR TNG300-1 TNG-Cluster`, `--limit N` (first N per source), `--workers`.
Outputs, per config, in `<data drive>/_domain_gap/preprocessed/<name>/`:

| File | Content |
|---|---|
| `inputs_{source}.npy` | float32 (N, grid, grid) model inputs in [0, 1] |
| `masks_{source}.npy` | uint8, 1 where the output pixel is covered |
| `manifest.parquet` / `.csv` | one row per image: identifiers, `index` into the arrays, redshift, exposure, centre and its method, field size, `native_pix_per_output`, coverage, stretch limits, flags (`status`, `low_coverage`, `upsampled`, `no_signal`, `usable`) |
| `run.json` | config, fitted intensity parameters, code version, counts |
| `embeddings_{source}.npy` | AstroCLIP embeddings, rows aligned with the inputs; `domain_gap.embed` also copies them, with the manifest, `run.json` and `embed.json`, to `outputs/embeddings/<name>/` in this worktree |
| `qa/` | `examples.png`, `pixels.png`, `profiles.png` |

The extraction (stage 1) is cached per image under `_stage1/<hash of the spatial settings>/`
and shared by configs that differ only in smoothing or intensity. Rerunning skips images
already extracted, so the mocks can be added as they finish.

## What the steps do

1. **Centre.**
   - LEMUR: the catalog X-ray centre.
   - Mocks: LEMUR's own `find_xray_peak` on the broad flux and exposure map, with the
     halo position as the prior. LEMUR uses the target position as its prior.
   - `center: halo` uses the potential minimum instead.
2. **Field.** A square of fixed physical size (`kpc`) or angle (`arcsec`, `arcmin`,
   `native_pixels`). The physical size uses the TNG cosmology (Planck15).
3. **Resample.**
   - Exact pixel overlap onto `grid` × `grid`, with no interpolation.
   - Each output pixel is Σ F·E / Σ E. For the broad band this is Σ(C − B) / Σ E.
   - The result is divided by the pixel area, giving surface brightness in
     ph cm⁻² s⁻¹ arcsec⁻² whatever the input binning.
   - Coverage is the covered fraction of each output pixel.
   - LEMUR keeps only a broad-band exposure map, so it weights every band on both sides.
4. **Mask and smooth.** Output pixels with coverage below `pixel_min` are masked. Gaussian
   smoothing is normalized over the mask, so field edges and chip gaps are not darkened.
5. **Intensity.** Both modes use LEMUR's asinh stretch.
   - `morphology`: per-image 5–99.7 percentiles of covered pixels.
   - `physical`: one vmin/vmax for all images. vmax is fitted from the pooled covered
     pixels, each source weighted equally, and recorded in `run.json`. Optionally
     (1+z)ⁿ dimming.
6. **Embed.** Three-channel replication and resize to 144 px with LEMUR's
   `to_model_batch`, then frozen AstroCLIP.

## Configs

| Config | Field | Grid | Weighting / smoothing | Stretch |
|---|---|---|---|---|
| `baseline` | 512 native px (4.2′) | 64 → 144 at embedding | plain mean / zero-padded σ = 1.5 px | per image, all positive pixels |
| `harmonized_morphology` | 500 kpc | 144 (3.5 kpc/px) | exposure / masked σ = 1.5 px (5.2 kpc) | per image, covered pixels |
| `harmonized_physical` | 500 kpc | 144 | as above | shared, fitted vmax |

## Verification

- `configs/baseline.yaml` reproduces LEMUR's current AstroCLIP preprocessing
  (`scripts/astroclip_xray_similarity.py`) exactly. On three LEMUR clusters the largest
  pixel difference is 0.000 and the correlation 1.0000.
- `tests/test_domain_gap_preprocess.py` (14 tests) covers:
  - overlap matrices and edge coverage;
  - Σ(C − B) / Σ E;
  - chip gaps;
  - masked smoothing;
  - agreement of the smoothing and stretch with LEMUR's functions;
  - the shared stretch and the equal-weight fit.
- A smoke run of all three configs (12 images per source) produced inputs, manifest, QA
  figures and embeddings.

## Mock background: the faint CXB (fixed 2026-10-16)

The first mocks kept the whole cosmic X-ray background, about 2 × 10⁻¹⁰ ph cm⁻² s⁻¹ arcsec⁻²
in 0.5–7 keV. The cause is in how the two backgrounds were built:

- The observations include SOXS's point sources and its unresolved component.
- The reference background had neither.
- LEMUR's blank-sky backgrounds have detected sources removed but keep the fainter CXB,
  so that part is subtracted from LEMUR.

The reference now includes the same faint part:
- SOXS's own source population below 10⁻¹⁵ erg cm⁻² s⁻¹ (0.5–2 keV), which is 27% of the
  point-source flux;
- SOXS's unresolved component;
- spread uniformly and observed for 2 Ms.

Brighter sources stay in the images, as in LEMUR. After the fix, the source-robust median
6–8′ from a z = 0.2 group falls from 2.4 × 10⁻¹⁰ to 4 × 10⁻¹¹. Older observations are
recomputed from their counts with `run --refit`. Their headers record `CXBLIMIT`.

## Open points

- **The 10⁻¹⁵ blank-sky removal limit is an assumption.** It is typical of 30–100 ks
  fields. A different limit moves part of the CXB between B and the images.
  - Only the reference changes, so `make_cxb_reference` plus `--refit` can redo it
    without re-simulating.
- **Matching.** Comparisons should use LEMUR clusters near the mock redshifts (±0.025 in
  the QA) and, where possible, similar exposure and ACIS-I. The manifest has the columns
  for this.
- **Three LEMUR clusters have z = 0.05 exactly,** which looks like a placeholder:
  - 1321045;
  - 1AXGJ0809072023;
  - 1E22157-04041E_7ba03.
- **Bands.** The configs use the broad band; set `band: soft` or `hard` for the others.

## Mass matching (2026-10-19)

`python -m domain_gap.mass_match` (figures and tables in `outputs/figures/mass/`).

- **Proxy.** The 0.5–7 keV photon luminosity within 250 kpc is measured identically on
  LEMUR and the mocks, from the 500 kpc extraction.
- **Calibration.** At each redshift the mocks give log M500 against log L. The relation
  has slope 0.47 and a scatter of 0.19–0.20 dex, and TNG300 and TNG-Cluster follow the
  same relation. Applied to LEMUR, it gives TNG-calibrated masses
  (`lemur_masses.csv`). These assume TNG's L–M relation holds for real clusters.
- **Masses.** The two simulations bracket LEMUR:

| | TNG300 | LEMUR (TNG-calibrated) | TNG-Cluster |
|---|---|---|---|
| Typical log M500 [M☉] | ~14.0 | z = 0.05: ~14.0, with groups down to 13; z = 0.1: ~14.3; z = 0.2: ~14.5 | ~14.7 |

- **Matching by reweighting.** The mocks are weighted to LEMUR's distribution in
  (log L, exposure) at each redshift, and the classifier and AUC use the weights. As a
  check, TNG300 is reweighted to TNG-Cluster's true M500.

Domain AUC, unweighted → mass-matched, harmonized_physical, z = 0.05 / 0.1 / 0.2:

| Pair | All | Mass-matched |
|---|---|---|
| TNG-Cluster vs TNG300 (true M500) | 0.91 / 0.90 / 0.90 | **0.56 / 0.52 / 0.54** |
| LEMUR vs TNG300 | 0.74 / 0.70 / 0.78 | 0.68 / 0.67 / 0.67 |
| LEMUR vs TNG-Cluster | 0.94 / 0.90 / 0.76 | 0.71 / 0.76 / 0.62 |

- **Mass drives the separation between the simulations.** At matched mass they are
  nearly indistinguishable in the physical config. Residuals in the other configs are
  0.59–0.67.
- **Mass explains much, not all, of the LEMUR–mock gap.** A residual AUC of about
  0.62–0.76 remains at matched luminosity and exposure. The next candidates are core
  structure (cool cores), point sources and faint or offset LEMUR fields, and
  observational differences (ACIS-S, multi-ObsID mosaics).

## Signal cut (2026-10-19)

`python -m domain_gap.signal` measures every image the same way, within 250 kpc
(`outputs/figures/signal/`):

- **S/N:** net counts over √counts;
- **point-source fraction:** the share of the aperture flux in compact sources, from
  LEMUR's own point-source detector.

`--signal-cut [--snr-min 10 --ps-max 0.5]` in `analyze_embeddings` and `mass_match`
applies the cut to LEMUR and the mocks alike.

- **Who passes:** 781 of 1,184 LEMUR clusters, 98% of TNG300 and 93% of TNG-Cluster.
- **Below S/N 10:** 143 LEMUR fields, mostly offset pointings and faint fields.
- **Point-source fraction above 0.5:** 343 LEMUR fields, including many galaxies and
  groups in the cluster category, with a pile-up near 1.
- **Caveat:** at z = 0.2 a few percent of TNG-Cluster images also exceed 0.5. This is
  probably compact cores being flagged, so the cut was also run at 0.8.
- **Result:** the mass-matched LEMUR–mock AUC barely changes (physical config,
  0.62–0.74 with the cut against 0.62–0.76 without). Most such fields have no mock
  counterpart at matched luminosity anyway. The remaining gap is not caused by faint or
  point-source-dominated LEMUR fields.

## Core structure (2026-10-19)

`python -m domain_gap.core` (figures and tables in `outputs/figures/core/`). The signal
cut is applied, since a central AGN raises c.

- **Concentration.** c = F(<40 kpc) / F(<250 kpc) around the X-ray peak, measured
  identically on every image. This is Santos et al.'s cool-core concentration with the
  outer radius limited by the 500 kpc field, so their thresholds do not carry over.
- **Validation.** In TNG-Cluster, c tracks the central cooling time closely: Spearman
  −0.94, −0.90 and −0.85 at z = 0.05, 0.1 and 0.2.
- **LEMUR against L-matched mocks.** At z = 0.05 and 0.1, LEMUR has a second population
  of highly concentrated clusters (c ≈ 0.2–0.5) that L-matched mocks almost never
  produce:

  | z | LEMUR median c | TNG300 median c | TNG-Cluster median c | LEMUR 75th pct | Mock 75th pct |
  |---|---|---|---|---|---|
  | 0.05 | 0.11 | 0.073 | 0.057 | 0.21 | 0.07–0.09 |
  | 0.2 | 0.075 | 0.083 | 0.068 | — | — |

  At z = 0.2 the two agree.
- **Matching on concentration as well.** Adding c to the reweighting (on top of L and
  exposure) brings the domain AUC of harmonized_physical to about 0.5: 0.39–0.54,
  against 0.62–0.76 with L and exposure only. At matched luminosity and core
  concentration, AstroCLIP no longer separates LEMUR from TNG. In the per-image-stretch
  configs the AUC falls but stays at 0.59–0.77.
- **Caveats:**
  - **Selection.** LEMUR clusters more concentrated than any L-matched mock drop out of
    the (L, c) matching. Up to half of LEMUR at z = 0.05 against TNG-Cluster drops out,
    and that is the cool-core excess itself.
  - **Target selection.** Low-z Chandra targets are largely X-ray selected, which favours
    cool cores. Many z ≈ 0.2 targets are SZ selected (PSZ2), and there LEMUR matches TNG.
    The excess may be partly selection rather than TNG physics.
  - **Noise.** Matched samples are small (tens to hundreds effective), so the AUCs are
    uncertain by roughly ±0.05–0.1. A bootstrap would quantify this.

## From the original setup to the matched comparison (2026-10-19)

`domain_gap.original_gap` uses the lemur-astroclip env and writes to
`outputs/figures/original/`. It measures the gap of the original experiment: LEMUR's own
embeddings against the student's surviving mock embeddings (`val_data300.pt`,
`val_datacluster.pt`). It then follows each step of this project.

Everything is at z = 0.05, the student's only redshift, with LEMUR within ±0.025 and the
mocks at 100 ks. The values are domain AUC.

| Step | LEMUR vs TNG300 | LEMUR vs TNG-Cluster | TNG-Cluster vs TNG300 | Same, at equal M500 |
|---|---|---|---|---|
| 0. Original setup (student mocks and PNG pipeline) | **0.999** | **1.000** | 0.81 | 0.68 |
| 1. Regenerated mocks, LEMUR preprocessing for both | 0.86 | 0.91 | 0.86 | 0.66 |
| 2. Harmonized morphology | 0.89 | 0.94 | 0.90 | 0.66 |
| 3. Harmonized physical | 0.73 | 0.93 | 0.90 | 0.54 |
| 4. + L and exposure matching (`domain_gap.core`, signal cut) | 0.71 | 0.64 | — | — |
| 5. + concentration matching | **0.50** | **0.39** | — | — |

The original setup separates LEMUR from the mocks perfectly. That separation comes from
the mocks and their preprocessing, not from the clusters:
- **Regeneration and identical preprocessing (step 1)** remove most of it.
- **Population matching (step 4)** removes most of what remains.
- **Core concentration (step 5)** removes the rest.

Between the two simulations, only the physical config (step 3) brings equal-mass TNG300
and TNG-Cluster close to indistinguishable.
