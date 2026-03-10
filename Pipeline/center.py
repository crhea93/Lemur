from pathlib import Path


def compute_center(
    cluster_name,
    image_path,
    initial_ra,
    initial_dec,
    db_service,
    fallback_ra=None,
    fallback_dec=None,
):
    """Placeholder center computation.

    For now this uses the best available sky position already derived by the
    pipeline and stores it as the canonical center. A later implementation can
    replace this with a dedicated center-finding algorithm while preserving the
    same DB contract.
    """
    center_ra = initial_ra if initial_ra is not None else fallback_ra
    center_dec = initial_dec if initial_dec is not None else fallback_dec
    if center_ra is None or center_dec is None:
        raise RuntimeError(
            f"Unable to compute center for {cluster_name}: no valid RA/DEC available."
        )

    db_service.upsert_center(
        cluster_name,
        center_ra=center_ra,
        center_dec=center_dec,
        center_x=None,
        center_y=None,
        method="placeholder_existing_centroid",
        image_path=str(Path(image_path)),
    )
    return db_service.get_center(cluster_name)
