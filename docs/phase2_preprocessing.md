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
| `manifest.parquet` / `.csv` | one row per image: identifiers, `index` into the arrays, redshift, exposure, centre and its method, field size, `native_pix_per_output`, coverage, stretch limits, flags (`status`, `low_coverage`, `upsampled`, `empty`, `usable`) |
| `run.json` | config, fitted intensity parameters, code version, counts |
| `embeddings_{source}.npy` | AstroCLIP embeddings, rows aligned with the inputs |
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
