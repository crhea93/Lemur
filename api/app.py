import io
import os
import re
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .db import DATA_DIR, DB_PATH, get_conn

app = FastAPI(title="Lemur API")

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR.parent / "Web"
PLOTS_DIR = WEB_DIR / "Cluster_plots"
FITS_DIR = Path(os.getenv("LEMUR_FITS_DIR", str(DATA_DIR / "fits"))).expanduser()


def fits_download_url(name: str) -> str:
    return f"/api/fits/{urllib.parse.quote(name)}/download"


def ensure_db():
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail="Database not found. Run api/ingest_sql_dump.py first.",
        )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/clusters")
def list_clusters():
    ensure_db()
    query = """
        SELECT
            c.ID,
            c.Name,
            c.redshift,
            c.RightAsc,
            c.Declination,
            c.R_cool_3,
            c.R_cool_7,
            c.csb_ct,
            c.csb_pho,
            c.csb_flux,
            GROUP_CONCAT(o.Obsid) AS Obsids
        FROM Clusters c
        LEFT JOIN Obsids o ON o.ClusterNumber = c.ID
        GROUP BY c.ID
        ORDER BY c.Name COLLATE NOCASE
    """
    with get_conn() as conn:
        rows = conn.execute(query).fetchall()

    results = []
    for row in rows:
        obsids = row["Obsids"].split(",") if row["Obsids"] else []
        results.append(
            {
                "ID": row["ID"],
                "Name": row["Name"],
                "redshift": row["redshift"],
                "RightAsc": row["RightAsc"],
                "Declination": row["Declination"],
                "R_cool_3": row["R_cool_3"],
                "R_cool_7": row["R_cool_7"],
                "csb_ct": row["csb_ct"],
                "csb_pho": row["csb_pho"],
                "csb_flux": row["csb_flux"],
                "Obsids": obsids,
                "fits_download_url": fits_download_url(row["Name"]),
            }
        )

    return results


@app.get("/api/clusters/{name}")
def cluster_detail(name: str):
    ensure_db()
    with get_conn() as conn:
        cluster = conn.execute(
            "SELECT * FROM Clusters WHERE Name = ?", (name,)
        ).fetchone()
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")

        obsids = [
            row["Obsid"]
            for row in conn.execute(
                "SELECT Obsid FROM Obsids WHERE ClusterNumber = ?",
                (cluster["ID"],),
            ).fetchall()
        ]

        regions = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM Region WHERE idCluster = ? ORDER BY idRegion",
                (cluster["ID"],),
            ).fetchall()
        ]

    plot_dir = PLOTS_DIR / name
    plots = []
    if plot_dir.exists():
        allowed = {"bkgsub_exp.png"}
        for filename in sorted(os.listdir(plot_dir)):
            lower = filename.lower()
            if not lower.endswith((".png", ".jpg", ".jpeg", ".svg", ".gif")):
                continue
            if (
                filename in allowed
                or lower.endswith("_lightcurve.png")
                or lower.endswith("_ccds.png")
            ):
                plots.append(filename)

    return {
        "cluster": dict(cluster),
        "obsids": obsids,
        "regions": regions,
        "fits_download_url": fits_download_url(cluster["Name"]),
        "plots": {
            "base_url": f"/Cluster_plots/{name}",
            "files": plots,
        },
    }


@app.get("/api/resolve-name")
def resolve_name(q: str = ""):
    q = (q or "").strip()
    if not q:
        return {"query": "", "names": []}

    names = {q}
    try:
        sesame_url = (
            "https://cds.unistra.fr/cgi-bin/nph-sesame/-oI/SNV?" + urllib.parse.quote(q)
        )
        req = urllib.request.Request(
            sesame_url, headers={"User-Agent": "LemurArchive/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
        for line in text.splitlines():
            match = re.match(r"^%I\S*\s+(.+)$", line.strip())
            if match:
                candidate = match.group(1).strip()
                if candidate:
                    names.add(candidate)
    except Exception:
        pass

    return {"query": q, "names": sorted(names)}


@app.get("/")
def index_page():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/cluster/{name}")
def cluster_page(name: str):
    return FileResponse(WEB_DIR / "cluster.html")


@app.get("/cluster.html")
def cluster_page_direct():
    return FileResponse(WEB_DIR / "cluster.html")


@app.get("/api/fits/{name}/download")
def download_fits(name: str):
    fits_dir = FITS_DIR / name
    if not fits_dir.exists() or not fits_dir.is_dir():
        raise HTTPException(status_code=404, detail="FITS directory not found")

    files = [
        path
        for path in fits_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".fits", ".fit", ".fts", ".gz"}
    ]
    if not files:
        raise HTTPException(status_code=404, detail="No FITS files found")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for path in files:
            zipf.write(path, arcname=path.name)

    zip_buffer.seek(0)
    headers = {"Content-Disposition": f"attachment; filename={name}_fits.zip"}
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=False), name="static")
