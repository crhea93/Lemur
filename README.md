# Lemur
X-ray Galaxy Cluster Archive with a FastAPI backend and a modern web UI.

Live cluster website: https://lemur-archive.lemur-xray.workers.dev

[![CI](https://github.com/crhea93/Lemur/actions/workflows/ci.yml/badge.svg)](https://github.com/crhea93/Lemur/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-pytest--cov-blue)](#development)
[![DOI](https://zenodo.org/badge/166745110.svg)](https://doi.org/10.5281/zenodo.18728228)

## Quick Start
1. Create the SQLite database from the SQL dump:
```bash
lemur-ingest-sql --sql lemur.sql
# or:
python3 api/ingest_sql_dump.py --sql lemur.sql
```

2. Run the API + static site:
```bash
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

3. Open:
- `http://localhost:8000/Table/index_table.html`
- `http://localhost:8000/cluster/Abell133`

Optional runtime paths:
- `LEMUR_DATA_DIR` (default: `api/data`)
- `LEMUR_DB_PATH` (default: `$LEMUR_DATA_DIR/lemur.db`)
- `LEMUR_FITS_DIR` (default: `$LEMUR_DATA_DIR/fits`)

## Install
From repo root:
```bash
pip install -e .
```

Optional extras:
```bash
pip install -e ".[pipeline,test]"
```

Installed CLI commands:
- `lemur-pipeline`
- `lemur-ingest-sql`

## Pipeline
Pipeline code lives in `Pipeline/` and is orchestrated by `Pipeline/pipeline.py`.

Run with an input file:
```bash
lemur-pipeline /path/to/input.i
```

Run by cluster + ObsIDs:
```bash
lemur-pipeline --cluster Abell133 --obsids 2203,9897
```

### Similar clusters (AstroCLIP embeddings)
`--compute-embeddings` cuts a region 512 native ACIS pixels (4.2') on a side
from each cluster's `broad_flux.img` around the canonical center, whatever the
image binning. Each cutout is area-resampled onto a common 3.936"/px grid,
smoothed, and asinh-stretched like the web image, then embedded with the
[AstroCLIP](https://github.com/PolymathicAI/AstroCLIP) image encoder
(resampled to its 144x144 input, X-ray band copied into 3 channels).
Embeddings are stored in `image_embedding`; the cosine top-k neighbors are
written to `similar_clusters` and served at `GET /api/clusters/{name}/similar`.

AstroCLIP was trained on optical Legacy Survey cutouts, so on Chandra images it
is out of distribution: treat neighbors as morphological similarity.

The canonical center (`Pipeline/center.py`) is the X-ray emission peak: a
band-pass smoothed flux image with chip edges (from `broad_thresh.expmap`) and
point sources masked, preferring the peak within 4' of the catalog position.

AstroCLIP needs its own environment. Its README pins torch 2.0, which predates
recent GPUs (e.g. RTX 50xx needs torch>=2.7 with CUDA 12.8); a newer torch works:
```bash
conda create -n lemur-astroclip python=3.11
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install lightning omegaconf fvcore iopath jaxtyping huggingface_hub astropy \
    scipy matplotlib "numpy<2" datasets scikit-image python-dotenv h5py joblib submitit
pip install --no-deps git+https://github.com/facebookresearch/dinov2.git@2302b6bf46953431b969155307b9bed152754069
pip install --no-deps git+https://github.com/PolymathicAI/AstroCLIP.git
```

Then run (the checkpoint downloads from `polymathic-ai/astroclip` on first use):
```bash
lemur-pipeline --compute-embeddings --defaults inputs/template.i \
    --embed-cutout-size 512 --embed-neighbors 10 [--embed-device cuda]
make sync-d1   # push similar_clusters to Cloudflare D1
```

## API
Primary endpoints:
- `GET /api/health`
- `GET /api/clusters`
- `GET /api/clusters/{name}`
- `GET /api/fits/{name}/download`
- `GET /api/stamps`

FITS downloads are served from `$LEMUR_FITS_DIR` (or `api/data/fits` by default).

Sync helper:
```bash
scripts/sync_fits.sh /path/to/fits_source
scripts/sync_fits.sh s3://my-bucket/fits
```

## Cloudflare Deployment
Cloudflare Worker + D1 setup is documented in:
- `cloudflare/README.md`

Useful shortcuts:
```bash
make deploy
make sync-all
make sync-d1
make sync-fits
make dry-run
```

## Development
For contribution workflow, linting, typing, and test commands, see:
- `CONTRIBUTING.md`

## Citation
If you use Lemur or its data products in your work, please cite the Zenodo record:
[doi:10.5281/zenodo.18728228](https://doi.org/10.5281/zenodo.18728228)

```bibtex
@software{rhea_lemur,
  author    = {Rhea, Carter Lee and Thibeault, Christian},
  title     = {Lemur: X-ray Galaxy Cluster Archive},
  publisher = {Zenodo},
  year      = {2026},
  doi       = {10.5281/zenodo.18728228},
  url       = {https://doi.org/10.5281/zenodo.18728228}
}
```
