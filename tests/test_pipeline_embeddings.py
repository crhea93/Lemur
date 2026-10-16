import numpy as np
import pytest

from Pipeline import db as db_module
from Pipeline import db_service as ds
from Pipeline import embeddings


def _service(tmp_path):
    mydb, mycursor, db_user, db_host, db_name = db_module.connect_db(
        {"db_engine": "sqlite", "sqlite_db_path": str(tmp_path / "lemur.db")},
        "",
    )
    return ds.DatabaseService(mydb, mycursor, db_user, "", db_host, db_name)


def _add_cluster(service, cluster_id, name, with_image_dir=None):
    service.mycursor.execute(
        "INSERT INTO Clusters (ID, Name, redshift) VALUES (%s, %s, %s)",
        (cluster_id, name, 0.05),
    )
    service.mydb.commit()
    service.upsert_center(
        name,
        center_ra=10.0 + cluster_id,
        center_dec=-5.0,
        center_x=None,
        center_y=None,
        method="test",
        image_path="x",
    )
    if with_image_dir is not None:
        cluster_dir = with_image_dir / name
        cluster_dir.mkdir(parents=True)
        (cluster_dir / "broad_flux.img").write_bytes(b"")


def test_stretch_image_maps_into_unit_interval_and_handles_nans():
    rng = np.random.default_rng(0)
    image = rng.exponential(scale=3.0, size=(64, 64)).astype(np.float32)
    image[0, 0] = np.nan
    out = embeddings.stretch_image(image)
    assert out.shape == image.shape
    assert out.dtype == np.float32
    assert np.all(np.isfinite(out))
    assert out.min() >= 0.0 and out.max() <= 1.0
    assert out.max() == pytest.approx(1.0)


def test_stretch_image_blank_input_returns_zeros():
    out = embeddings.stretch_image(np.zeros((8, 8)))
    assert np.all(out == 0.0)


def test_nearest_neighbors_excludes_self_and_orders_by_similarity():
    names = ["A", "B", "C", "D"]
    vectors = np.array(
        [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [-1.0, 0.0]], dtype=np.float32
    )
    result = embeddings.nearest_neighbors(names, vectors, k=2)
    assert [n for n, _ in result["A"]] == ["B", "C"]
    assert [n for n, _ in result["C"]] == ["B", "A"]
    for name, items in result.items():
        assert name not in [n for n, _ in items]
        sims = [s for _, s in items]
        assert sims == sorted(sims, reverse=True)


def test_nearest_neighbors_clamps_k_and_handles_singletons():
    vectors = np.eye(3, dtype=np.float32)
    result = embeddings.nearest_neighbors(["A", "B", "C"], vectors, k=10)
    assert all(len(items) == 2 for items in result.values())
    assert embeddings.nearest_neighbors(["A"], vectors[:1]) == {"A": []}


def test_embedding_blob_roundtrip():
    vector = np.array([0.5, -1.25, 3.0], dtype=np.float32)
    blob = embeddings.embedding_to_blob(vector)
    np.testing.assert_array_equal(embeddings.blob_to_embedding(blob), vector)


def test_compute_embeddings_stores_vectors_and_neighbors(tmp_path):
    service = _service(tmp_path)
    home = tmp_path / "chandra"
    for i, name in enumerate(["A", "B", "C"], start=1):
        _add_cluster(service, i, name, with_image_dir=home)
    _add_cluster(service, 4, "NoImage")

    # Encode each image as (mean, 1 - mean) so A and B land close together.
    fills = {"A": 0.9, "B": 0.8, "C": 0.1}
    loader_calls = []

    def fake_loader(path, ra, dec, size):
        name = path.split("/")[-2]
        loader_calls.append((name, ra, dec, size))
        return np.full((size, size), fills[name], dtype=np.float32) + np.eye(size)

    def fake_encode(images):
        return np.array([[img.mean(), 1.0 - img.mean()] for img in images])

    unresolved = embeddings.compute_embeddings(
        ["A", "B", "C", "NoImage"],
        str(home),
        service,
        fake_encode,
        cutout_size=16,
        k=2,
        cutout_loader=fake_loader,
    )

    assert unresolved == ["NoImage"]
    assert loader_calls[0] == ("A", 11.0, -5.0, 16)

    stored = service.get_embeddings(embeddings.MODEL_NAME)
    assert sorted(stored) == ["A", "B", "C"]
    for blob in stored.values():
        assert np.linalg.norm(embeddings.blob_to_embedding(blob)) == pytest.approx(
            1.0, abs=1e-5
        )

    service.mycursor.execute(
        "SELECT NeighborName, rank FROM similar_clusters "
        "WHERE ClusterName = %s ORDER BY rank",
        ("A",),
    )
    rows = service.mycursor.fetchall()
    assert [r[0] for r in rows] == ["B", "C"]
    assert [r[1] for r in rows] == [1, 2]


def test_compute_embeddings_rerun_replaces_neighbors(tmp_path):
    service = _service(tmp_path)
    home = tmp_path / "chandra"
    for i, name in enumerate(["A", "B"], start=1):
        _add_cluster(service, i, name, with_image_dir=home)

    def run():
        embeddings.compute_embeddings(
            ["A", "B"],
            str(home),
            service,
            lambda images: np.ones((len(images), 4)),
            cutout_size=8,
            k=5,
            cutout_loader=lambda *a: np.ones((8, 8), dtype=np.float32),
        )

    run()
    run()
    service.mycursor.execute("SELECT COUNT(*) FROM similar_clusters")
    assert service.mycursor.fetchone()[0] == 2
    service.mycursor.execute("SELECT COUNT(*) FROM image_embedding")
    assert service.mycursor.fetchone()[0] == 2


def test_area_resample_preserves_mean_and_shape():
    rng = np.random.default_rng(1)
    image = rng.poisson(0.05, size=(512, 512)).astype(np.float32)
    out = embeddings.area_resample(image, 64)
    assert out.shape == (64, 64)
    assert out.mean() == pytest.approx(image.mean(), rel=1e-5)
    # Exact block averaging when the factor is an integer.
    np.testing.assert_allclose(
        out, image.reshape(64, 8, 64, 8).mean(axis=(1, 3)), rtol=1e-5
    )


def test_area_resample_handles_non_integer_factors():
    out = embeddings.area_resample(np.ones((65, 70)), 64)
    assert out.shape == (64, 64)
    np.testing.assert_allclose(out, 1.0, rtol=1e-6)


def test_common_grid_size_matches_eight_times_binning():
    assert embeddings.common_grid_size(512) == 64
