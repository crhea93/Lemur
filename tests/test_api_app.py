import io
import sqlite3
import zipfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import app as app_module
from api import ingest_sql_dump as ingest


def _make_test_db(db_path: Path):
    conn = sqlite3.connect(db_path)
    try:
        ingest.create_schema(conn)
        conn.execute(
            """
            INSERT INTO Clusters (
                ID, Name, redshift, RightAsc, Declination,
                R_cool_3, R_cool_7, csb_ct, csb_pho, csb_flux
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "Abell133", 0.0566, "01:02:03", "-01:02:03", 10.0, 20.0, 1.0, 2.0, 3.0),
        )
        conn.execute(
            "INSERT INTO Obsids (ClusterNumber, Obsid) VALUES (?, ?)",
            (1, 2203),
        )
        conn.execute(
            """
            INSERT INTO Region (
                idCluster, idRegion, Area, Temp, Temp_min, Temp_max,
                Abundance, Ab_min, Ab_max, Norm, Norm_min, Norm_max, Flux,
                Luminosity, ReducedChiSquare, Agn_bool, Density, Dens_min,
                Dens_max, Pressure, Press_min, Press_max, Entropy,
                Entropy_min, Entropy_max, T_cool, T_cool_min, T_cool_max,
                AGN, R_in, R_out
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                1,
                1,
                100.0,
                5.0,
                4.5,
                5.5,
                0.3,
                0.2,
                0.4,
                1.0,
                0.9,
                1.1,
                1e-12,
                2e43,
                1.05,
                0,
                0.01,
                0.009,
                0.011,
                0.02,
                0.019,
                0.021,
                100.0,
                95.0,
                105.0,
                2.0,
                1.8,
                2.2,
                0,
                0.0,
                10.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "lemur.db"
    _make_test_db(db_path)

    plots_dir = tmp_path / "plots"
    plots_dir.mkdir()
    cluster_plot_dir = plots_dir / "Abell133"
    cluster_plot_dir.mkdir()
    (cluster_plot_dir / "bkgsub_exp.png").write_bytes(b"img")
    (cluster_plot_dir / "foo_lightcurve.png").write_bytes(b"img")
    (cluster_plot_dir / "ignore.txt").write_text("x", encoding="utf-8")

    fits_dir = tmp_path / "fits"
    (fits_dir / "Abell133").mkdir(parents=True)
    (fits_dir / "Abell133" / "a.fits").write_bytes(b"fits-a")
    (fits_dir / "Abell133" / "b.fit").write_bytes(b"fits-b")

    @contextmanager
    def _get_conn():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    monkeypatch.setattr(app_module, "DB_PATH", db_path)
    monkeypatch.setattr(app_module, "get_conn", _get_conn)
    monkeypatch.setattr(app_module, "PLOTS_DIR", plots_dir)
    monkeypatch.setattr(app_module, "FITS_DIR", fits_dir)

    with TestClient(app_module.app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_clusters_returns_obsids_and_fits_url(client):
    response = client.get("/api/clusters")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["Name"] == "Abell133"
    assert payload[0]["Obsids"] == ["2203"]
    assert payload[0]["fits_download_url"] == "/api/fits/Abell133/download"


def test_cluster_detail_returns_regions_and_filtered_plots(client):
    response = client.get("/api/clusters/Abell133")
    assert response.status_code == 200
    payload = response.json()
    assert payload["cluster"]["Name"] == "Abell133"
    assert payload["obsids"] == [2203]
    assert len(payload["regions"]) == 1
    assert payload["plots"]["files"] == ["bkgsub_exp.png", "foo_lightcurve.png"]


def test_cluster_detail_not_found(client):
    response = client.get("/api/clusters/Nope")
    assert response.status_code == 404
    assert response.json()["detail"] == "Cluster not found"


def test_resolve_name_empty_query_does_not_call_network(client):
    response = client.get("/api/resolve-name?q=")
    assert response.status_code == 200
    assert response.json() == {"query": "", "names": []}


def test_fits_download_returns_zip_from_local_files(client):
    response = client.get("/api/fits/Abell133/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    buffer = io.BytesIO(response.content)
    with zipfile.ZipFile(buffer) as zf:
        names = sorted(zf.namelist())
    assert names == ["a.fits", "b.fit"]
