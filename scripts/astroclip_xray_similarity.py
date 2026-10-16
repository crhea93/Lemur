#!/usr/bin/env python
"""Morphological similarity of Chandra X-ray images with AstroCLIP.

Standalone version of the similarity search in the LEMUR catalog
(https://github.com/crhea93/Lemur, Pipeline/center.py and
Pipeline/embeddings.py). For each input image it

  1. finds the X-ray center: the peak of the diffuse emission, ignoring point
     sources, chip edges and chip-to-chip background differences;
  2. cuts out a 512 x 512 native ACIS pixel (4.2' x 4.2') region around it,
     resamples it to 3.936"/pixel, smooths it and applies an asinh stretch;
  3. embeds the cutout with the AstroCLIP image encoder (Parker et al. 2024,
     MNRAS 531, 4990), giving a 1024-dimensional unit vector;
  4. lists every image's nearest neighbors by cosine similarity.

AstroCLIP was trained on optical DESI Legacy Survey images, so X-ray images are
far outside its training data. Use the neighbors as a morphological ranking,
not a calibrated physical match, and do not interpret the absolute similarity
values: only their order is meaningful.

Input
-----
FITS images of exposure-corrected (ideally background-subtracted) flux on a
celestial WCS, e.g. the LEMUR downloads ``<name>_broad_flux.fits.gz`` or the
``broad_flux.img`` of a CIAO merge_obs/fluximage run. For each image the script
also looks for an exposure map next to it (``<name>_broad_expmap.fits[.gz]`` for
``<name>_broad_flux.fits[.gz]``, or ``broad_thresh.expmap`` next to
``broad_flux.img``); it is optional but makes the center more robust. The
observer's target position (RA_TARG/DEC_TARG in the header) is used as a prior
for the center when present.

Output (in --out)
-----------------
  centers.csv     name, X-ray center (RA, Dec in degrees, 0-based pixel x, y),
                  method (xray_peak, or target_position if no peak was found)
  embeddings.npz  names and the (N, 1024) float32 unit-vector embeddings
  neighbors.csv   name, rank, neighbor, cosine similarity (top --k per image)

Usage
-----
    python astroclip_xray_similarity.py images/*_broad_flux.fits.gz --out results

Installation (conda; AstroCLIP's own pins are too old for current GPUs)
------------------------------------------------------------------------
    conda create -n astroclip python=3.11 && conda activate astroclip
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
    pip install lightning omegaconf fvcore iopath jaxtyping huggingface_hub \\
        astropy scipy "numpy<2" "datasets>=3" scikit-image python-dotenv h5py joblib submitit
    pip install --no-deps "git+https://github.com/facebookresearch/dinov2.git@2302b6bf46953431b969155307b9bed152754069"
    pip install --no-deps "git+https://github.com/PolymathicAI/AstroCLIP.git"

The AstroCLIP checkpoint (polymathic-ai/astroclip on Hugging Face, ~1 GB) is
downloaded on first use; pass --checkpoint to use a local copy. A GPU is used
when available; on a CPU expect roughly a second per image.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

ACIS_PIXEL_ARCSEC = 0.492

# ---------------------------------------------------------------------------
# X-ray center (LEMUR Pipeline/center.py)
# ---------------------------------------------------------------------------

# Working resolution for peak finding; matches an 8x-binned ACIS image.
WORK_PIXEL_ARCSEC = 3.936
# Band-pass scales: cluster-core scale minus a large-scale background, so
# uniformly bright chips (e.g. back-illuminated S3) and point sources don't win.
CORE_SIGMA_ARCSEC = 30.0
BACKGROUND_SIGMA_ARCSEC = 120.0
REFINE_SIGMA_ARCSEC = 8.0
REFINE_RADIUS_ARCSEC = 45.0
# Point-source suppression: compact excess of the small-scale over the local
# smoothing, flagged at POINT_SOURCE_NSIGMA robust sigmas and masked out.
POINT_SOURCE_SIGMA_ARCSEC = 4.0
LOCAL_SIGMA_ARCSEC = 20.0
POINT_SOURCE_NSIGMA = 5.0
POINT_SOURCE_DILATE_ARCSEC = 8.0
# Prior: prefer the peak within PRIOR_RADIUS_ARCSEC of the target position
# unless the best peak on the whole array is GLOBAL_OVERRIDE times stronger.
PRIOR_RADIUS_ARCSEC = 240.0
GLOBAL_OVERRIDE = 2.0
# Distance from the chip/exposure edge excluded from the peak search.
EDGE_ARCSEC = 30.0
# Pixels with exposure below this fraction of the typical exposure are masked.
EXPOSURE_FRACTION = 0.1


def _block_reduce(array, factor, func):
    if factor <= 1:
        return array
    ny, nx = (array.shape[0] // factor) * factor, (array.shape[1] // factor) * factor
    trimmed = array[:ny, :nx]
    return func(
        trimmed.reshape(ny // factor, factor, nx // factor, factor), axis=(1, 3)
    )


def _masked_smooth(data, mask, sigma_pix):
    """Mask-aware Gaussian smoothing, so chip edges are not darkened."""
    from scipy.ndimage import gaussian_filter

    weights = gaussian_filter(mask.astype(np.float64), sigma_pix)
    smoothed = gaussian_filter(np.where(mask, data, 0.0), sigma_pix)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = smoothed / weights
    out[weights < 1e-3] = 0.0
    return out


def _point_source_mask(binned, mask, work_arcsec):
    from scipy.ndimage import binary_dilation

    small = _masked_smooth(binned, mask, POINT_SOURCE_SIGMA_ARCSEC / work_arcsec)
    local = _masked_smooth(binned, mask, LOCAL_SIGMA_ARCSEC / work_arcsec)
    excess = small - local
    values = excess[mask]
    if values.size == 0:
        return np.zeros_like(mask)
    median = np.median(values)
    sigma = 1.4826 * np.median(np.abs(values - median))
    if sigma <= 0:
        return np.zeros_like(mask)
    sources = (excess > median + POINT_SOURCE_NSIGMA * sigma) & (small > 2.0 * local)
    iterations = max(1, int(round(POINT_SOURCE_DILATE_ARCSEC / work_arcsec)))
    return binary_dilation(sources, iterations=iterations) & mask


def find_xray_peak(data, exposure=None, pixel_arcsec=ACIS_PIXEL_ARCSEC, prior_xy=None):
    """Peak of the diffuse emission in a flux image.

    :param data: 2D flux image
    :param exposure: optional exposure map on the same pixel grid
    :param pixel_arcsec: pixel size of ``data`` in arcseconds
    :param prior_xy: optional prior position, 0-based pixels of ``data``
    :return: (x, y) peak in 0-based pixel coordinates of ``data``, or None
    """
    from scipy.ndimage import binary_erosion, label

    data = np.nan_to_num(np.asarray(data, dtype=np.float64), nan=0.0)
    factor = max(1, int(round(WORK_PIXEL_ARCSEC / pixel_arcsec)))
    work_arcsec = pixel_arcsec * factor
    binned = _block_reduce(data, factor, np.mean)

    if exposure is not None and np.shape(exposure) == data.shape:
        exp = _block_reduce(
            np.nan_to_num(np.asarray(exposure, dtype=np.float64)), factor, np.mean
        )
        positive = exp[exp > 0]
        if positive.size == 0:
            return None
        mask = exp > EXPOSURE_FRACTION * np.percentile(positive, 90)
    else:
        # Without an exposure map, treat regions with any counts nearby as covered.
        mask = (
            _masked_smooth((binned > 0).astype(float), np.ones_like(binned, bool), 2.0)
            > 0.05
        )

    covered = binary_erosion(mask, iterations=max(1, int(EDGE_ARCSEC / work_arcsec)))
    if not covered.any():
        covered = mask
    if not covered.any():
        return None
    # The global search uses only the largest contiguous exposed region (the
    # aimpoint array), so detached off-axis chips with higher background can't win.
    search = covered
    labels, count = label(covered)
    if count > 1:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        search = labels == np.argmax(sizes)

    # Smooth only over covered pixels that are not point sources.
    weights = mask & ~_point_source_mask(binned, mask, work_arcsec)
    band_pass = _masked_smooth(
        binned, weights, CORE_SIGMA_ARCSEC / work_arcsec
    ) - _masked_smooth(binned, weights, BACKGROUND_SIGMA_ARCSEC / work_arcsec)
    global_map = np.where(search, band_pass, -np.inf)
    by, bx = np.unravel_index(np.argmax(global_map), global_map.shape)

    if prior_xy is not None:
        yy, xx = np.indices(band_pass.shape)
        px = (prior_xy[0] + 0.5) / factor - 0.5
        py = (prior_xy[1] + 0.5) / factor - 0.5
        near = covered & (
            (xx - px) ** 2 + (yy - py) ** 2 <= (PRIOR_RADIUS_ARCSEC / work_arcsec) ** 2
        )
        if near.any():
            local_map = np.where(near, band_pass, -np.inf)
            ly, lx = np.unravel_index(np.argmax(local_map), local_map.shape)
            local_value = band_pass[ly, lx]
            if local_value > 0 and band_pass[by, bx] <= GLOBAL_OVERRIDE * local_value:
                by, bx = ly, lx

    # Refine on a finer smoothing scale within a small radius of the coarse peak.
    fine = _masked_smooth(binned, weights, REFINE_SIGMA_ARCSEC / work_arcsec)
    yy, xx = np.indices(fine.shape)
    radius = REFINE_RADIUS_ARCSEC / work_arcsec
    fine[((xx - bx) ** 2 + (yy - by) ** 2 > radius**2) | ~mask] = -np.inf
    by, bx = np.unravel_index(np.argmax(fine), fine.shape)

    # Center of the binned pixel in native 0-based pixel coordinates.
    return (bx + 0.5) * factor - 0.5, (by + 0.5) * factor - 0.5


def xray_center(image_path, expmap_path=None):
    """(ra, dec, x, y, method) of the X-ray center of a FITS image.

    Falls back to the target position (RA_TARG/DEC_TARG) when no peak is found;
    returns None if neither is available.
    """
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from astropy.io import fits
    from astropy.wcs import WCS
    from astropy.wcs.utils import proj_plane_pixel_scales

    with fits.open(image_path) as hdul:
        data = hdul[0].data
        header = hdul[0].header
    wcs = WCS(header).celestial
    pixel_arcsec = float(abs(proj_plane_pixel_scales(wcs)[0]) * 3600.0)
    exposure = None
    if expmap_path is not None:
        with fits.open(expmap_path) as hdul:
            exposure = hdul[0].data

    target = None
    if header.get("RA_TARG") is not None and header.get("DEC_TARG") is not None:
        target = SkyCoord(
            float(header["RA_TARG"]) * u.deg, float(header["DEC_TARG"]) * u.deg
        )
    prior_xy = (
        tuple(float(v) for v in wcs.world_to_pixel(target))
        if target is not None
        else None
    )

    peak = find_xray_peak(data, exposure, pixel_arcsec, prior_xy=prior_xy)
    if peak is not None:
        sky = wcs.pixel_to_world(*peak)
        return (
            float(sky.icrs.ra.deg),
            float(sky.icrs.dec.deg),
            float(peak[0]),
            float(peak[1]),
            "xray_peak",
        )
    if target is not None:
        return (
            float(target.ra.deg),
            float(target.dec.deg),
            None,
            None,
            "target_position",
        )
    return None


# ---------------------------------------------------------------------------
# Cutouts, preprocessing and AstroCLIP (LEMUR Pipeline/embeddings.py)
# ---------------------------------------------------------------------------

HF_REPO_ID = "polymathic-ai/astroclip"
HF_CHECKPOINT = "astroclip.ckpt"
MODEL_INPUT_SIZE = 144
COMMON_PIXEL_ARCSEC = 3.936
SMOOTH_SIGMA = 1.5  # Gaussian smoothing on the common grid, in grid pixels
DEFAULT_CUTOUT_SIZE = 512  # native ACIS pixels
DEFAULT_NEIGHBORS = 10


def make_cutout(image_path, center_ra, center_dec, size=DEFAULT_CUTOUT_SIZE):
    """Square cutout ``size`` native ACIS pixels (size * 0.492") on a side.

    Its pixel shape depends on the image binning. Regions off the detector are
    zero-filled so the center stays in the middle.
    """
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from astropy.io import fits
    from astropy.nddata import Cutout2D
    from astropy.wcs import WCS

    with fits.open(image_path) as hdul:
        data = np.array(hdul[0].data, dtype=np.float32)
        wcs = WCS(hdul[0].header)
    cutout = Cutout2D(
        data,
        position=SkyCoord(center_ra * u.deg, center_dec * u.deg, frame="fk5"),
        size=u.Quantity((size, size)) * ACIS_PIXEL_ARCSEC * u.arcsec,
        wcs=wcs.celestial,
        mode="partial",
        fill_value=0.0,
    )
    return np.asarray(cutout.data, dtype=np.float32)


def common_grid_size(size=DEFAULT_CUTOUT_SIZE):
    """Pixels per side of a ``size`` native-pixel cutout on the common grid."""
    return max(1, int(round(size * ACIS_PIXEL_ARCSEC / COMMON_PIXEL_ARCSEC)))


def _area_weights(n_in, n_out):
    """(n_out, n_in) matrix averaging input pixels by fractional overlap."""
    edges_in = np.arange(n_in + 1) / n_in
    edges_out = np.arange(n_out + 1) / n_out
    lo = np.maximum(edges_out[:-1, None], edges_in[None, :-1])
    hi = np.minimum(edges_out[1:, None], edges_in[None, 1:])
    overlap = np.clip(hi - lo, 0.0, None)
    return overlap / overlap.sum(axis=1, keepdims=True)


def area_resample(image, out_size):
    """Flux-conserving (mean-preserving) resample to ``out_size`` x ``out_size``."""
    data = np.nan_to_num(np.asarray(image, dtype=np.float64), nan=0.0)
    rows = _area_weights(data.shape[0], out_size)
    cols = _area_weights(data.shape[1], out_size)
    return (rows @ data @ cols.T).astype(np.float32)


def gaussian_smooth(image, sigma):
    """Separable Gaussian smoothing with zero padding."""
    if sigma <= 0:
        return np.asarray(image, dtype=np.float32)
    radius = max(1, int(np.ceil(3 * sigma)))
    x = np.arange(-radius, radius + 1)
    kernel = np.exp(-0.5 * (x / sigma) ** 2)
    kernel /= kernel.sum()
    data = np.asarray(image, dtype=np.float64)
    data = np.apply_along_axis(np.convolve, 0, data, kernel, mode="same")
    data = np.apply_along_axis(np.convolve, 1, data, kernel, mode="same")
    return data.astype(np.float32)


def stretch_image(image, lower_pct=5.0, upper_pct=99.7, asinh_a=0.08):
    """Percentile-normalize and asinh-stretch into [0, 1].

    The per-image normalization removes differences in exposure time and flux,
    so the embedding responds to the shape of the emission.
    """
    data = np.nan_to_num(np.asarray(image, dtype=np.float32), nan=0.0)
    positive = data[np.isfinite(data) & (data > 0)]
    if positive.size == 0:
        return np.zeros_like(data, dtype=np.float32)
    vmin = float(np.percentile(positive, lower_pct))
    vmax = float(np.percentile(positive, upper_pct))
    if vmax <= vmin:
        vmin, vmax = float(positive.min()), float(positive.max())
    if vmax <= vmin:
        return np.zeros_like(data, dtype=np.float32)
    scaled = np.clip((data - vmin) / (vmax - vmin), 0.0, 1.0)
    # Same definition as astropy.visualization.AsinhStretch.
    return (np.arcsinh(scaled / asinh_a) / np.arcsinh(1.0 / asinh_a)).astype(np.float32)


def prepare_image(cutout, grid_size, smooth_sigma=SMOOTH_SIGMA):
    """Resample onto the common grid, smooth, then stretch into [0, 1].

    Smoothing turns sparse single-photon pixels into visible diffuse emission;
    without it low-count images stretch to near-black frames that all embed alike.
    """
    return stretch_image(
        gaussian_smooth(area_resample(cutout, grid_size), smooth_sigma)
    )


def to_model_batch(images, input_size=MODEL_INPUT_SIZE):
    """Stack 2D images into a (N, 3, input_size, input_size) tensor."""
    import torch
    import torch.nn.functional as F

    batch = torch.from_numpy(np.stack(images).astype(np.float32)).unsqueeze(1)
    batch = F.interpolate(
        batch,
        size=(input_size, input_size),
        mode="bilinear",
        antialias=True,
        align_corners=False,
    )
    return batch.repeat(1, 3, 1, 1).clamp_(0.0, 1.0)


def make_astroclip_encoder(checkpoint_path=None, device=None, batch_size=16):
    """Return ``encode(images) -> (N, D) array`` backed by AstroCLIP."""
    import torch
    from astroclip.models import AstroClipModel

    if checkpoint_path is None:
        from huggingface_hub import hf_hub_download

        checkpoint_path = hf_hub_download(HF_REPO_ID, HF_CHECKPOINT)
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    # The published checkpoint pickles full modules, which torch>=2.6 rejects
    # under its weights_only default. Only load checkpoints you trust.
    model = AstroClipModel.load_from_checkpoint(
        checkpoint_path, map_location=device, weights_only=False
    )
    model.eval()
    model.to(device)

    def encode(images):
        chunks = []
        with torch.no_grad():
            for start in range(0, len(images), batch_size):
                batch = to_model_batch(images[start : start + batch_size])
                out = model(batch.to(device), input_type="image")
                chunks.append(out.reshape(batch.shape[0], -1).cpu().numpy())
        return np.concatenate(chunks, axis=0)

    return encode


def normalize_embeddings(embeddings):
    embeddings = np.asarray(embeddings, dtype=np.float32)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    return embeddings / np.clip(norms, 1e-12, None)


def nearest_neighbors(names, embeddings, k=DEFAULT_NEIGHBORS):
    """Cosine top-k neighbors of every entry, excluding itself.

    Returns ``{name: [(neighbor, similarity), ...]}`` by decreasing similarity.
    """
    if len(names) < 2:
        return {name: [] for name in names}
    unit = normalize_embeddings(embeddings)
    similarity = unit @ unit.T
    np.fill_diagonal(similarity, -np.inf)
    k = min(k, len(names) - 1)
    order = np.argsort(-similarity, axis=1, kind="stable")[:, :k]
    return {
        name: [(names[j], float(similarity[i, j])) for j in order[i]]
        for i, name in enumerate(names)
    }


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _strip_fits_suffix(name):
    for suffix in (".gz", ".fits", ".fit", ".fts", ".img"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def object_name(path):
    """LEMUR download names: '<name>_broad_flux.fits.gz' -> '<name>'."""
    path = Path(path)
    stem = _strip_fits_suffix(path.name)
    if stem == "broad_flux":  # <object folder>/broad_flux.img
        return path.parent.name
    for suffix in ("_broad_flux", "_flux"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def find_expmap(path):
    """Exposure map that goes with a flux image, if one sits next to it."""
    path = Path(path)
    stem = _strip_fits_suffix(path.name)
    candidates = []
    if stem == "broad_flux":
        candidates.append(path.with_name("broad_thresh.expmap"))
    if stem.endswith("_flux"):
        base = stem[: -len("_flux")]
        candidates += [
            path.with_name(f"{base}_expmap{ext}")
            for ext in (".fits", ".fits.gz", ".img")
        ]
    for candidate in candidates:
        for option in (candidate, candidate.with_name(candidate.name + ".gz")):
            if option.exists():
                return option
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("images", nargs="+", help="FITS flux images (one per object)")
    parser.add_argument("--out", default="astroclip_results", help="Output directory")
    parser.add_argument(
        "--k", type=int, default=DEFAULT_NEIGHBORS, help="Neighbors per image"
    )
    parser.add_argument(
        "--cutout-size",
        type=int,
        default=DEFAULT_CUTOUT_SIZE,
        help='Cutout side in native ACIS pixels (0.492")',
    )
    parser.add_argument(
        "--checkpoint", help="Local AstroCLIP checkpoint (default: download)"
    )
    parser.add_argument(
        "--device", help="torch device, e.g. cuda or cpu (default: cuda if available)"
    )
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    grid_size = common_grid_size(args.cutout_size)

    names, images, centers = [], [], []
    for image_path in args.images:
        name = object_name(image_path)
        if name in names:
            print(
                f"skipping {image_path}: another image is already named {name}",
                file=sys.stderr,
            )
            continue
        try:
            center = xray_center(image_path, find_expmap(image_path))
            if center is None:
                raise ValueError("no X-ray peak and no RA_TARG/DEC_TARG in the header")
            cutout = make_cutout(image_path, center[0], center[1], args.cutout_size)
        except Exception as exc:
            print(f"skipping {image_path}: {exc}", file=sys.stderr)
            continue
        names.append(name)
        centers.append(center)
        images.append(prepare_image(cutout, grid_size))
    if not names:
        sys.exit("no images could be used")

    with open(out / "centers.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["name", "center_ra", "center_dec", "center_x", "center_y", "method"]
        )
        for name, (ra, dec, x, y, method) in zip(names, centers):
            writer.writerow(
                [
                    name,
                    f"{ra:.6f}",
                    f"{dec:.6f}",
                    "" if x is None else f"{x:.1f}",
                    "" if y is None else f"{y:.1f}",
                    method,
                ]
            )

    print(f"Embedding {len(images)} images with AstroCLIP...")
    encode = make_astroclip_encoder(args.checkpoint, args.device, args.batch_size)
    embeddings = normalize_embeddings(encode(images))
    np.savez(out / "embeddings.npz", names=np.array(names), embeddings=embeddings)

    neighbors = nearest_neighbors(names, embeddings, k=args.k)
    with open(out / "neighbors.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "rank", "neighbor", "similarity"])
        for name in names:
            for rank, (neighbor, similarity) in enumerate(neighbors[name], start=1):
                writer.writerow([name, rank, neighbor, f"{similarity:.4f}"])
    print(
        f"Wrote {out}/centers.csv, embeddings.npz and neighbors.csv for {len(names)} images."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
