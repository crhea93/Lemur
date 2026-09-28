.PHONY: help deploy sync-all sync-d1 sync-fits dry-run check-chandra-dir \
	astroclip-env pull-db centers embeddings similar serve publish-similar \
	flux-images merge-duplicates publish

# Load local runtime env vars if present (see .env.example).
-include .env.local

LEMUR_DB_PATH ?= api/data/lemur.db
ASTROCLIP_ENV ?= lemur-astroclip
ASTROCLIP_PYTHON ?= $(HOME)/miniconda3/envs/$(ASTROCLIP_ENV)/bin/python
EMBED_CUTOUT_SIZE ?= 512
EMBED_NEIGHBORS ?= 10
PORT ?= 8000
export LEMUR_DATA_DIR LEMUR_DB_PATH LEMUR_FITS_DIR

SYNC_SCRIPT := ./cloudflare/scripts/sync_cloudflare_data.sh
WRANGLER := $(shell command -v wrangler >/dev/null 2>&1 && echo wrangler || echo npx --yes wrangler)
PIPELINE := $(ASTROCLIP_PYTHON) -W ignore -m Pipeline

help:
	@echo "Similar clusters (AstroCLIP), in order:"
	@echo "  make astroclip-env    - One-time: create the conda env ($(ASTROCLIP_ENV))"
	@echo "  make pull-db          - Download the live D1 database to $(LEMUR_DB_PATH)"
	@echo "  make similar          - Recompute centers + embeddings + neighbors locally"
	@echo "  make serve            - Preview the site at http://localhost:$(PORT)"
	@echo "  make publish-similar  - Push similar_clusters to D1 and deploy the site"
	@echo "  make publish          - Push ALL tables to D1, fix merged FITS zips, deploy"
	@echo ""
	@echo "Data maintenance:"
	@echo "  make flux-images      - Build broad_flux.img (CIAO) for clusters with raw data"
	@echo "  make merge-duplicates - Apply scripts/duplicate_merges.json to data folders"
	@echo ""
	@echo "Other targets:"
	@echo "  make centers / make embeddings - Run either half of 'make similar'"
	@echo "  make deploy     - Deploy Worker + static assets"
	@echo "  make sync-all   - Sync D1 schema/data and FITS uploads"
	@echo "  make sync-d1    - Sync D1 schema/data only (replaces ALL tables)"
	@echo "  make sync-fits  - Sync FITS uploads only"
	@echo "  make dry-run    - Preview sync commands without executing"

deploy:
	$(WRANGLER) deploy

sync-all:
	$(SYNC_SCRIPT)

sync-d1:
	$(SYNC_SCRIPT) --skip-fits

sync-fits:
	$(SYNC_SCRIPT) --skip-d1

dry-run:
	$(SYNC_SCRIPT) --dry-run

astroclip-env:
	ASTROCLIP_ENV=$(ASTROCLIP_ENV) ./scripts/setup_astroclip_env.sh

pull-db:
	@if [ -e "$(LEMUR_DB_PATH)" ] && [ "$(FORCE)" != "1" ]; then \
		echo "$(LEMUR_DB_PATH) exists; rerun with FORCE=1 to replace it."; exit 1; fi
	@mkdir -p "$(dir $(LEMUR_DB_PATH))"
	$(WRANGLER) d1 export lemur-db --remote --output "$(LEMUR_DB_PATH).sql"
	rm -f "$(LEMUR_DB_PATH)"
	sqlite3 "$(LEMUR_DB_PATH)" < "$(LEMUR_DB_PATH).sql"
	rm -f "$(LEMUR_DB_PATH).sql"
	@echo "Loaded live D1 data into $(LEMUR_DB_PATH)"

check-chandra-dir:
	@test -n "$(LEMUR_CHANDRA_DIR)" || { \
		echo "Set LEMUR_CHANDRA_DIR (folder with <cluster>/broad_flux.img) in .env.local"; exit 1; }
	@for dir in $(subst :, ,$(LEMUR_CHANDRA_DIR)); do test -d "$$dir" || { \
		echo "Data folder not found: $$dir (is the drive mounted?)"; exit 1; }; done
	@test -e "$(LEMUR_DB_PATH)" || { echo "$(LEMUR_DB_PATH) missing; run 'make pull-db'"; exit 1; }

centers: check-chandra-dir
	$(PIPELINE) --recompute-centers --home-dir "$(LEMUR_CHANDRA_DIR)" \
		--sqlite-db "$(LEMUR_DB_PATH)"

embeddings: check-chandra-dir
	$(PIPELINE) --compute-embeddings --home-dir "$(LEMUR_CHANDRA_DIR)" \
		--sqlite-db "$(LEMUR_DB_PATH)" \
		--embed-cutout-size $(EMBED_CUTOUT_SIZE) --embed-neighbors $(EMBED_NEIGHBORS)

similar: centers embeddings

serve:
	@echo "Open http://localhost:$(PORT)/cluster/Abell133 (Ctrl+C to stop)"
	$(ASTROCLIP_PYTHON) -m uvicorn api.app:app --host 127.0.0.1 --port $(PORT)

publish-similar:
	$(SYNC_SCRIPT) --similar-only
	$(WRANGLER) deploy

# Full publish: replaces Clusters/Obsids/Region/similar_clusters in D1 with the
# local DB, so start from `make pull-db` rather than an old copy.
publish:
	$(SYNC_SCRIPT) --skip-fits
	python3 scripts/merge_duplicate_clusters.py r2
	$(WRANGLER) deploy

CIAO_ENV ?= ciao
flux-images: check-chandra-dir
	$(HOME)/miniconda3/bin/conda run --no-capture-output -n $(CIAO_ENV) python \
		scripts/build_flux_images.py --sqlite-db "$(LEMUR_DB_PATH)" \
		--data-dir "$(firstword $(subst :, ,$(LEMUR_CHANDRA_DIR)))" \
		--search-dirs "$(LEMUR_CHANDRA_DIR)"

# Re-apply the saved merge plan to data folders, e.g. after mounting another drive.
merge-duplicates: check-chandra-dir
	python3 scripts/merge_duplicate_clusters.py apply --only-data \
		--data-dir "$(LEMUR_CHANDRA_DIR)"
