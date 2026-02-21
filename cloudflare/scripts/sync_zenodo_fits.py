#!/usr/bin/env python3
import argparse
import hashlib
import http.client
import json
import random
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

FITS_SUFFIXES = {".fits", ".fit", ".fts", ".gz"}


def format_bytes(num_bytes):
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{num_bytes} B"


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def iter_clusters(fits_root):
    for cluster_dir in sorted(p for p in fits_root.iterdir() if p.is_dir()):
        files = sorted(
            [
                f
                for f in cluster_dir.iterdir()
                if f.is_file() and f.suffix.lower() in FITS_SUFFIXES
            ],
            key=lambda p: p.name,
        )
        if files:
            yield cluster_dir.name, files


def create_zip(cluster_name, files, tmp_dir):
    zip_path = tmp_dir / f"{cluster_name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for file_path in files:
            zipf.write(file_path, arcname=file_path.name)
    return zip_path


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def request_json(method, url, token=None, payload=None):
    headers = {}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url=url, method=method, data=data, headers=headers)
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    return json.loads(body) if body else {}


def _backoff_sleep(attempt, base_delay):
    delay = base_delay * (2 ** max(0, attempt - 1))
    jitter = random.uniform(0, min(1.0, delay * 0.2))
    time.sleep(delay + jitter)


def _is_retryable_status(status_code):
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504, 520, 521, 522, 524}


def request_binary_put(
    url,
    token,
    file_path,
    max_retries=5,
    base_delay_seconds=2.0,
    timeout_seconds=120,
    progress_label="",
):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise RuntimeError(f"Expected HTTPS upload URL, got: {url}")
    host = parsed.netloc
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"

    size = file_path.stat().st_size
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/zip",
        "Content-Length": str(size),
    }
    label = progress_label or file_path.name

    last_error = None
    for attempt in range(1, max_retries + 1):
        conn = http.client.HTTPSConnection(host, timeout=timeout_seconds)
        try:
            conn.putrequest("PUT", target)
            for key, value in headers.items():
                conn.putheader(key, value)
            conn.endheaders()

            sent = 0
            next_report_pct = 5
            print(
                f"[upload] {label}: attempt {attempt}/{max_retries}, "
                f"size={format_bytes(size)}"
            )
            with open(file_path, "rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    conn.send(chunk)
                    sent += len(chunk)
                    if size > 0:
                        pct = int((sent * 100) / size)
                        if pct >= next_report_pct:
                            print(
                                f"[upload] {label}: {pct}% "
                                f"({format_bytes(sent)}/{format_bytes(size)})"
                            )
                            next_report_pct += 5

            if sent >= size:
                print(
                    f"[upload] {label}: 100% "
                    f"({format_bytes(sent)}/{format_bytes(size)})"
                )

            response = conn.getresponse()
            response.read()
            status = response.status
            if 200 <= status < 300:
                print(f"[upload] {label}: complete (HTTP {status})")
                return
            if _is_retryable_status(status) and attempt < max_retries:
                print(
                    f"[retry] {label} failed with HTTP {status}; "
                    f"attempt {attempt}/{max_retries}"
                )
                _backoff_sleep(attempt, base_delay_seconds)
                continue
            raise RuntimeError(f"Upload failed with HTTP {status}: {response.reason}")
        except (
            BrokenPipeError,
            ConnectionError,
            TimeoutError,
            OSError,
            http.client.HTTPException,
        ) as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            print(
                f"[retry] {label} connection error: {exc}; "
                f"attempt {attempt}/{max_retries}"
            )
            _backoff_sleep(attempt, base_delay_seconds)
        finally:
            conn.close()

    if last_error is not None:
        raise RuntimeError(
            f"Upload failed after {max_retries} attempts: {last_error}"
        ) from last_error
    raise RuntimeError(f"Upload failed after {max_retries} attempts.")


def infer_download_url(zenodo_api_base, record_id, filename, published_payload):
    files = published_payload.get("files") or []
    for file_info in files:
        links = file_info.get("links") or {}
        if isinstance(links.get("download"), str):
            return links["download"]

    base = zenodo_api_base.rstrip("/")
    if base.endswith("/api"):
        base = base[: -len("/api")]

    return f"{base}/records/{record_id}/files/{urllib.parse.quote(filename)}?download=1"


def public_base_url(zenodo_api_base):
    base = zenodo_api_base.rstrip("/")
    if base.endswith("/api"):
        base = base[: -len("/api")]
    return base


def upload_cluster_zip(zip_path, cluster_name, args):
    deposition = request_json(
        "POST",
        f"{args.zenodo_api_base.rstrip('/')}/deposit/depositions",
        token=args.zenodo_token,
        payload={},
    )
    dep_id = deposition["id"]
    bucket_url = deposition["links"]["bucket"]
    filename = zip_path.name

    request_binary_put(
        f"{bucket_url}/{urllib.parse.quote(filename)}",
        token=args.zenodo_token,
        file_path=zip_path,
        max_retries=args.upload_retries,
        base_delay_seconds=args.upload_retry_base_delay_seconds,
        timeout_seconds=args.upload_timeout_seconds,
        progress_label=cluster_name,
    )

    metadata = {
        "title": f"Lemur FITS: {cluster_name}",
        "upload_type": "dataset",
        "description": (
            f"FITS archive for Lemur cluster {cluster_name}. "
            "Contains cleaned 0.5-7.0 keV unbinned image products."
        ),
        "creators": [{"name": "Lemur Archive"}],
        "keywords": ["Lemur", "X-ray", "Galaxy Cluster", "FITS"],
    }
    if args.zenodo_community:
        metadata["communities"] = [{"identifier": args.zenodo_community}]

    request_json(
        "PUT",
        f"{args.zenodo_api_base.rstrip('/')}/deposit/depositions/{dep_id}",
        token=args.zenodo_token,
        payload={"metadata": metadata},
    )

    published = request_json(
        "POST",
        f"{args.zenodo_api_base.rstrip('/')}/deposit/depositions/{dep_id}/actions/publish",
        token=args.zenodo_token,
        payload={},
    )

    record_id = published.get("id", dep_id)
    url = infer_download_url(args.zenodo_api_base, record_id, filename, published)
    return {"record_id": record_id, "url": url, "filename": filename}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Upload per-cluster FITS ZIPs to Zenodo and build links manifest."
    )
    parser.add_argument("--fits-root", required=True, help="Root FITS directory.")
    parser.add_argument(
        "--links-file",
        required=True,
        help="Output JSON map: cluster name -> Zenodo download URL.",
    )
    parser.add_argument(
        "--state-file",
        required=True,
        help="State JSON used for change detection.",
    )
    parser.add_argument(
        "--zenodo-api-base",
        default="https://zenodo.org/api",
        help="Zenodo API base URL.",
    )
    parser.add_argument(
        "--zenodo-token",
        default="",
        help="Zenodo personal access token.",
    )
    parser.add_argument(
        "--zenodo-community",
        default="",
        help="Optional Zenodo community identifier.",
    )
    parser.add_argument(
        "--upload-retries",
        type=int,
        default=5,
        help="Maximum upload retry attempts for transient failures.",
    )
    parser.add_argument(
        "--upload-retry-base-delay-seconds",
        type=float,
        default=2.0,
        help="Base delay in seconds for exponential backoff between upload retries.",
    )
    parser.add_argument(
        "--upload-timeout-seconds",
        type=int,
        default=120,
        help="Socket timeout in seconds for each upload attempt.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    fits_root = Path(args.fits_root).expanduser()
    links_file = Path(args.links_file).expanduser()
    state_file = Path(args.state_file).expanduser()

    if not fits_root.exists():
        raise RuntimeError(f"FITS root not found: {fits_root}")

    if not args.dry_run and not args.zenodo_token:
        raise RuntimeError("Zenodo token is required unless --dry-run is set.")

    previous_state = load_json(state_file)
    next_state = {}
    links = {}

    uploaded = 0
    reused = 0
    skipped = 0

    with tempfile.TemporaryDirectory(prefix="lemur_zenodo_") as tmp:
        tmp_dir = Path(tmp)
        for cluster_name, files in iter_clusters(fits_root):
            zip_path = create_zip(cluster_name, files, tmp_dir)
            sha256 = sha256_file(zip_path)

            prior = previous_state.get(cluster_name, {})
            prior_sha = prior.get("sha256")
            prior_url = prior.get("url")
            prior_record_id = prior.get("record_id")

            if prior_sha == sha256 and isinstance(prior_url, str) and prior_url:
                links[cluster_name] = prior_url
                next_state[cluster_name] = {
                    "sha256": sha256,
                    "url": prior_url,
                    "record_id": prior_record_id,
                    "filename": zip_path.name,
                    "updated_at": prior.get("updated_at", utc_now()),
                }
                reused += 1
                print(f"[reuse] {cluster_name} (unchanged)")
                continue

            if args.dry_run:
                dry_url = (
                    f"{public_base_url(args.zenodo_api_base)}"
                    f"/records/DRYRUN/files/{urllib.parse.quote(zip_path.name)}?download=1"
                )
                links[cluster_name] = dry_url
                next_state[cluster_name] = {
                    "sha256": sha256,
                    "url": dry_url,
                    "record_id": "DRYRUN",
                    "filename": zip_path.name,
                    "updated_at": utc_now(),
                }
                skipped += 1
                print(f"[dry-run] would upload {cluster_name} ({len(files)} files)")
                continue

            result = upload_cluster_zip(zip_path, cluster_name, args)
            links[cluster_name] = result["url"]
            next_state[cluster_name] = {
                "sha256": sha256,
                "url": result["url"],
                "record_id": result["record_id"],
                "filename": result["filename"],
                "updated_at": utc_now(),
            }
            uploaded += 1
            print(f"[upload] {cluster_name} -> record {result['record_id']}")

    print(f"Summary: uploaded={uploaded} reused={reused} dry_run={skipped}")
    if args.dry_run:
        print("Dry run complete. No files were written.")
        return

    write_json(links_file, links)
    write_json(state_file, next_state)
    print(f"Wrote links file: {links_file}")
    print(f"Wrote state file: {state_file}")


if __name__ == "__main__":
    main()
