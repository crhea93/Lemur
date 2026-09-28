"""AstroCLIP image embeddings and nearest-neighbor "similar clusters".

Each cluster's ``broad_flux.img`` is cut out around the canonical center,
stretched to [0, 1], and encoded with the AstroCLIP image encoder. The
embeddings are stored in ``image_embedding`` and a cosine top-k neighbor list
is written to ``similar_clusters`` for the API/website.

AstroCLIP was trained on DESI Legacy Survey g/r/z cutouts, so Chandra
broad-band images are out of distribution: the single X-ray band is replicated
into three channels and the cutout is resampled to the 144x144 input size the
encoder was trained on.

Cutout sizes are in native ACIS pixels (0.492"), so a 512 pixel cutout always
covers 4.2' whatever the binning of broad_flux.img. Every cutout is first
area-resampled onto a common 8x-binned grid (3.936"/px) and only then
stretched, so 1x- and 8x-binned images look alike to the encoder and the
stretch percentiles are not dominated by single-photon pixels. Treat neighbors as morphological similarity, not a
calibrated physical match.

Heavy dependencies (torch, astroclip, astropy, huggingface_hub) are imported
lazily so the numpy-only helpers stay importable in lightweight environments.
"""

import numpy as np
from cluster_paths import resolve_cluster_file

MODEL_NAME = "astroclip-chandra-broad"
HF_REPO_ID = "polymathic-ai/astroclip"
HF_CHECKPOINT = "astroclip.ckpt"
MODEL_INPUT_SIZE = 144
ACIS_PIXEL_ARCSEC = 0.492
COMMON_PIXEL_ARCSEC = 3.936
# Gaussian smoothing on the common grid before stretching, in grid pixels.
SMOOTH_SIGMA = 1.5
DEFAULT_CUTOUT_SIZE = 512
DEFAULT_NEIGHBORS = 10


def _sky_coord(ra, dec):
    """Build a SkyCoord from degrees or sexagesimal strings (``hh:mm:ss``)."""
    from astropy import units as u
    from astropy.coordinates import SkyCoord

    if isinstance(ra, str) and ":" in ra:
        return SkyCoord(ra, str(dec), unit=(u.hourangle, u.deg), frame="fk5")
    return SkyCoord(float(ra) * u.deg, float(dec) * u.deg, frame="fk5")


def make_cutout(image_path, center_ra, center_dec, size=DEFAULT_CUTOUT_SIZE):
    """Return a square cutout ``size`` native ACIS pixels on a side.

    The cutout spans ``size * 0.492`` arcsec regardless of the image binning,
    so its pixel shape depends on the image. RA/Dec may be degrees or
    sexagesimal strings, as stored in Clusters.

    Regions falling off the detector are zero-filled so the cluster center
    stays at the middle of the cutout.
    """
    from astropy import units as u
    from astropy.io import fits
    from astropy.nddata import Cutout2D
    from astropy.wcs import WCS

    with fits.open(image_path) as hdul:
        data = np.array(hdul[0].data, dtype=np.float32)
        wcs = WCS(hdul[0].header)
    coord = _sky_coord(center_ra, center_dec)
    cutout = Cutout2D(
        data,
        position=coord,
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
    """Separable Gaussian smoothing with zero padding (numpy only)."""
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


def prepare_image(cutout, grid_size, smooth_sigma=SMOOTH_SIGMA):
    """Resample onto the common grid, smooth, then stretch into [0, 1].

    Smoothing (as in ``imaging.create_src_img``) turns sparse single-photon
    pixels into visible diffuse emission; without it low-count observations
    stretch to near-black frames that all embed identically.
    """
    return stretch_image(
        gaussian_smooth(area_resample(cutout, grid_size), smooth_sigma)
    )


def stretch_image(image, lower_pct=5.0, upper_pct=99.7, asinh_a=0.08):
    """Percentile-normalize and asinh-stretch an image into [0, 1].

    Mirrors the display stretch in ``imaging.create_src_img`` so the encoder
    sees the same diffuse structure a person sees on the cluster page. The
    per-image normalization also removes exposure-time differences.
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
    stretched = np.arcsinh(scaled / asinh_a) / np.arcsinh(1.0 / asinh_a)
    return stretched.astype(np.float32)


def to_model_batch(images, input_size=MODEL_INPUT_SIZE):
    """Stack equally sized 2D images into a (N, 3, input_size, input_size) tensor."""
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


def load_astroclip(checkpoint_path=None, device=None):
    """Load the AstroCLIP model, downloading the checkpoint if needed."""
    import torch
    from astroclip.models import AstroClipModel

    if checkpoint_path is None:
        from huggingface_hub import hf_hub_download

        checkpoint_path = hf_hub_download(HF_REPO_ID, HF_CHECKPOINT)
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    # The published checkpoint pickles full modules (e.g. ImageHead), which
    # torch>=2.6 rejects under its weights_only default. Only load trusted files.
    model = AstroClipModel.load_from_checkpoint(
        checkpoint_path, map_location=device, weights_only=False
    )
    model.eval()
    model.to(device)
    return model, device


def make_astroclip_encoder(checkpoint_path=None, device=None, batch_size=16):
    """Return ``encode(images) -> np.ndarray`` backed by AstroCLIP."""
    import torch

    model, device = load_astroclip(checkpoint_path, device)

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
    """Cosine top-k neighbors for every entry, excluding itself.

    Returns ``{name: [(neighbor_name, similarity), ...]}`` sorted by
    decreasing similarity.
    """
    if len(names) != len(embeddings):
        raise ValueError("names and embeddings must have the same length.")
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


def embedding_to_blob(vector):
    return np.asarray(vector, dtype="<f4").tobytes()


def blob_to_embedding(blob):
    return np.frombuffer(blob, dtype="<f4")


def compute_embeddings(
    names,
    home_dir,
    db_service,
    encode,
    cutout_size=DEFAULT_CUTOUT_SIZE,
    k=DEFAULT_NEIGHBORS,
    cutout_loader=make_cutout,
):
    """Embed each cluster's broad_flux.img and rebuild the neighbor table.

    ``encode`` maps a list of stretched 2D images to an (N, D) array; pass
    ``make_astroclip_encoder()`` in production. Returns the list of clusters
    that could not be embedded.
    """
    grid_size = common_grid_size(cutout_size)
    embedded_names = []
    images = []
    metadata = []
    unresolved = []
    for name in names:
        image_path = resolve_cluster_file(home_dir, name)
        center = db_service.get_center(name)
        if (
            image_path is None
            or center is None
            or center.get("center_ra") is None
            or center.get("center_dec") is None
        ):
            unresolved.append(name)
            continue
        try:
            cutout = cutout_loader(
                str(image_path), center["center_ra"], center["center_dec"], cutout_size
            )
        except Exception as exc:
            print(f"  Could not cut out {name}: {exc}")
            unresolved.append(name)
            continue
        embedded_names.append(name)
        images.append(prepare_image(cutout, grid_size))
        metadata.append((center["center_ra"], center["center_dec"], str(image_path)))

    if images:
        print(f"Embedding {len(images)} cutouts with AstroCLIP...")
        vectors = normalize_embeddings(encode(images))
        for name, vector, (ra, dec, path) in zip(embedded_names, vectors, metadata):
            db_service.upsert_embedding(
                name,
                model=MODEL_NAME,
                embedding=embedding_to_blob(vector),
                dim=int(vector.shape[0]),
                cutout_size=int(cutout_size),
                center_ra=ra,
                center_dec=dec,
                image_path=path,
            )

    # Neighbors span every stored embedding, not just this run's batch.
    stored = db_service.get_embeddings(MODEL_NAME)
    all_names = list(stored)
    if all_names:
        matrix = np.stack([blob_to_embedding(stored[n]) for n in all_names])
        neighbors = nearest_neighbors(all_names, matrix, k=k)
        db_service.replace_similar_clusters(MODEL_NAME, neighbors)
        print(f"Wrote top-{k} neighbors for {len(all_names)} clusters.")
    return unresolved
