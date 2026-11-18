"""Create an unpublished Zenodo draft for a LEMUR data release.

Creates the deposition with its metadata and a reserved DOI, uploads every
file in RELEASE_DIR, and prints the draft's URL and DOI. It never publishes:
review the draft on zenodo.org and press Publish there.

The personal access token (scopes deposit:write and deposit:actions) is read
from $ZENODO_TOKEN or ~/.config/zenodo/token and is never printed.

    python scripts/zenodo_release.py paper/release_dr1            # zenodo.org
    python scripts/zenodo_release.py paper/release_dr1 --sandbox  # sandbox.zenodo.org, for a dry run
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

CREATORS = [
    {"name": "Rhea, Carter Lee", "affiliation": "Dragonfly Focused Research Organization"},
    {"name": "Hlavacek-Larrondo, Julie", "affiliation": "Université de Montréal"},
    {"name": "Prunier, Marine", "affiliation": "MIT Kavli Institute for Astrophysics and Space Research"},
    {"name": "Choi, Hyunseop", "affiliation": "University of Michigan"},
    {"name": "Donahue, Megan", "affiliation": "Michigan State University"},
    {"name": "Thibeault, Christian", "affiliation": "Université de Montréal"},
]
DESCRIPTION = """<p>Catalog tables of LEMUR data release 1 (DR1): a searchable archive of
uniformly reduced, merged <i>Chandra</i> ACIS images of galaxies and galaxy
clusters. The tables give, for each object, its class, target position, X-ray
center, redshift, merged ObsIDs and clean exposure, a link to its page in the
web archive (which serves the background-subtracted, exposure-corrected images
in 0.5-7, 0.5-2 and 2-7 keV with their counts, background and exposure maps),
its ten most similar objects, and its AstroCLIP image embedding. See README.md.</p>
<p>Web archive: <a href="https://lemur-archive.lemur-xray.workers.dev/">https://lemur-archive.lemur-xray.workers.dev/</a>.
Code: <a href="https://github.com/crhea93/Lemur">https://github.com/crhea93/Lemur</a>.</p>"""
METADATA = {
    "upload_type": "dataset",
    "title": "LEMUR Data Release 1: catalog of merged Chandra images of galaxies and galaxy clusters",
    "creators": CREATORS,
    "description": DESCRIPTION,
    "access_right": "open",
    "license": "cc-by-4.0",
    "version": "DR1",
    "keywords": ["X-ray astronomy", "Chandra", "galaxy clusters", "galaxies", "catalog", "AstroCLIP"],
    "related_identifiers": [
        {"identifier": "https://github.com/crhea93/Lemur", "relation": "isSupplementTo", "scheme": "url"},
        {"identifier": "10.5281/zenodo.18728228", "relation": "isSupplementTo", "scheme": "doi"},
        {"identifier": "https://lemur-archive.lemur-xray.workers.dev/", "relation": "isSupplementTo", "scheme": "url"},
    ],
    "prereserve_doi": True,
}


def token():
    value = os.environ.get("ZENODO_TOKEN")
    path = Path.home() / ".config" / "zenodo" / "token"
    if not value and path.exists():
        value = path.read_text().strip()
    if not value:
        sys.exit("Set ZENODO_TOKEN or write the token to ~/.config/zenodo/token")
    return value


def request(method, url, auth, data=None, content_type="application/json"):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {auth}")
    if data is not None:
        req.add_header("Content-Type", content_type)
    with urllib.request.urlopen(req, timeout=600) as resp:
        body = resp.read()
    return json.loads(body) if body else {}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("--sandbox", action="store_true", help="use sandbox.zenodo.org")
    args = parser.parse_args()
    files = sorted(p for p in args.release_dir.iterdir() if p.is_file())
    if not files:
        sys.exit(f"No files in {args.release_dir}")
    api = "https://sandbox.zenodo.org/api" if args.sandbox else "https://zenodo.org/api"
    auth = token()

    deposition = request(
        "POST", f"{api}/deposit/depositions", auth, json.dumps({"metadata": METADATA}).encode()
    )
    bucket = deposition["links"]["bucket"]
    for path in files:
        request("PUT", f"{bucket}/{path.name}", auth, path.read_bytes(), "application/octet-stream")
        print(f"  uploaded {path.name} ({path.stat().st_size / 1e6:.1f} MB)")
    doi = deposition.get("metadata", {}).get("prereserve_doi", {}).get("doi")
    print(f"Draft (not published): {deposition['links']['html']}")
    print(f"Reserved DOI: {doi}")


if __name__ == "__main__":
    main()
