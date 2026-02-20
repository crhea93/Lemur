.PHONY: help deploy sync-all sync-d1 sync-fits dry-run

SYNC_SCRIPT := ./cloudflare/scripts/sync_cloudflare_data.sh

help:
	@echo "Targets:"
	@echo "  make deploy     - Deploy Worker + static assets"
	@echo "  make sync-all   - Sync D1 schema/data and Zenodo FITS uploads"
	@echo "  make sync-d1    - Sync D1 schema/data only"
	@echo "  make sync-fits  - Sync Zenodo FITS uploads only"
	@echo "  make dry-run    - Preview sync commands without executing"

deploy:
	wrangler deploy

sync-all:
	$(SYNC_SCRIPT)

sync-d1:
	$(SYNC_SCRIPT) --skip-zenodo

sync-fits:
	$(SYNC_SCRIPT) --skip-d1

dry-run:
	$(SYNC_SCRIPT) --dry-run
