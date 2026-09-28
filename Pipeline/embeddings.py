"""AstroCLIP image embeddings and nearest-neighbor "similar clusters".

Each cluster's ``broad_flux.img`` is cut out around the canonical center,
stretched to [0, 1], and encoded with the AstroCLIP image encoder. The
embeddings are stored in ``image_embedding`` and a cosine top-k neighbor list
is written to ``similar_clusters`` for the API/website.

AstroCLIP was trained on DESI Legacy Survey g/r/z cutouts, so Chandra
broad-band images are out of distribution: the single X-ray band is replicated
into three channels and the cutout is resampled to the 144x144 input size the
encoder was trained on. Treat neighbors as morphological similarity, not a
calibrated physical match.

Heavy dependencies (torch, astroclip, astropy, huggingface_hub) are imported
lazily so the numpy-only helpers stay importable in lightweight environments.
"""

from pathlib import Path

import numpy as np

MODEL_NAME = "astroclip-chandra-broad"
HF_REPO_ID = "polymathic-ai/astroclip"
HF_CHECKPOINT = "astroclip.ckpt"
MODEL_INPUT_SIZE = 144
DEFAULT_CUTOUT_SIZE = 512
DEFAULT_NEIGHBORS = 10


def make_cutout(image_path, center_ra, center_dec, size=DEFAULT_CUTOUT_SIZE):
    """Return a ``size`` x ``size`` cutout centered on (RA, Dec) in degrees.

    Regions falling off the detector are zero-filled so every cutout has the
    same shape and the cluster center stays at the middle pixel.
    """
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from astropy.io import fits
    from astropy.nddata import Cutout2D
    from astropy.wcs import WCS

    with fits.open(image_path) as hdul:
        data = np.array(hdul[0].data, dtype=np.float32)
        wcs = WCS(hdul[0].header)
    coord = SkyCoord(center_ra * u.deg, center_dec * u.deg, frame="fk5")
    cutout = Cutout2D(
        data,
        position=coord,
        size=(size, size),
        wcs=wcs,
        mode="partial",
        fill_value=0.0,
    )
    return np.asarray(cutout.data, dtype=np.float32)


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
    """Stack stretched 2D images into a (N, 3, input_size, input_size) tensor."""
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
    model = AstroClipModel.load_from_checkpoint(checkpoint_path, map_location=device)
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
    embedded_names = []
    images = []
    metadata = []
    unresolved = []
    for name in names:
        image_path = Path(home_dir) / name / "broad_flux.img"
        center = db_service.get_center(name)
        if (
            not image_path.exists()
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
        images.append(stretch_image(cutout))
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
