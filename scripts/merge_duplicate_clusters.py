"""Merge clusters stored twice under equivalent names (A2029 / Abell2029).

Two steps, so the same decisions can be applied to another data drive later:

  plan   Group Clusters by normalized name and write scripts/duplicate_merges.json.
         The survivor is the entry processed with the most distinct ObsIDs
         (ties: has web plots, has an image on disk, already canonically named).
         It is renamed to Abell<N> (or the best-cased spelling for non-Abell
         names) and keeps its own ObsIDs; the other entries are dropped.
  r2     Copy each renamed survivor's FITS zip in R2 to its canonical key, so the
         Worker does not serve the dropped entry's zip (run before deploying).
  apply  Apply the plan to the local DB, Web/Cluster_plots (git mv / git rm) and,
         with --data-dir, to data folders: the survivor's folder is renamed and
         dropped folders are moved to <data-dir>/_duplicates/ (never deleted).
         Every folder move is appended to <data-dir>/_duplicates/moves.log.
"""

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Pipeline"))
from cluster_paths import normalize_cluster_name  # noqa: E402

PLAN_PATH = ROOT / "scripts" / "duplicate_merges.json"
PLOTS_DIR = ROOT / "Web" / "Cluster_plots"
NAME_TABLES = [
    ("cluster_center", "ClusterName"),
    ("double_beta_fit", "ClusterName"),
    ("image_embedding", "ClusterName"),
    ("csb", "ClusterName"),
    ("r_cool", "ClusterName"),
    ("similar_clusters", "ClusterName"),
    ("similar_clusters", "NeighborName"),
]


def canonical_name(names):
    key = normalize_cluster_name(names[0])
    abell = re.fullmatch(r"a(\d+)", key)
    if abell:
        return f"Abell{abell.group(1)}"
    # Non-Abell: prefer mixed case with the most capitals (ComaCluster, SgrA).
    return max(names, key=lambda n: (not n.isupper(), sum(c.isupper() for c in n)))


def make_plan(db_path, data_dirs):
    con = sqlite3.connect(db_path)
    rows = con.execute(
        """
        SELECT c.ID, c.Name, COUNT(DISTINCT o.Obsid)
        FROM Clusters c LEFT JOIN Obsids o ON o.ClusterNumber = c.ID
        GROUP BY c.ID
        """
    ).fetchall()
    con.close()
    groups = defaultdict(list)
    for cluster_id, name, n_obsids in rows:
        groups[normalize_cluster_name(name)].append((cluster_id, name, n_obsids))

    plan = []
    for members in groups.values():
        if len(members) < 2:
            continue
        names = [m[1] for m in members]
        target = canonical_name(names)

        def rank(member):
            _, name, n_obsids = member
            has_image = any(
                (Path(d) / name / "broad_flux.img").exists() for d in data_dirs
            )
            return (
                n_obsids,
                (PLOTS_DIR / name).is_dir(),
                has_image,
                name == target,
            )

        survivor = max(members, key=rank)
        plan.append(
            {
                "canonical": target,
                "survivor": {"id": survivor[0], "name": survivor[1]},
                "dropped": [
                    {"id": m[0], "name": m[1]} for m in members if m is not survivor
                ],
            }
        )
    return sorted(plan, key=lambda p: p["canonical"].lower())


def table_exists(con, table):
    return (
        con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        is not None
    )


def apply_db(con, plan):
    for item in plan:
        for dropped in item["dropped"]:
            con.execute("DELETE FROM Obsids WHERE ClusterNumber = ?", (dropped["id"],))
            con.execute("DELETE FROM Region WHERE idCluster = ?", (dropped["id"],))
            con.execute("DELETE FROM Clusters WHERE ID = ?", (dropped["id"],))
            for table, column in NAME_TABLES:
                if table_exists(con, table):
                    con.execute(
                        f"DELETE FROM {table} WHERE {column} = ?", (dropped["name"],)
                    )
        old, new = item["survivor"]["name"], item["canonical"]
        if old != new:
            con.execute(
                "UPDATE Clusters SET Name = ? WHERE ID = ?",
                (new, item["survivor"]["id"]),
            )
            for table, column in NAME_TABLES:
                if table_exists(con, table):
                    con.execute(
                        f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                        (new, old),
                    )
    con.commit()


def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True)


def apply_plots(plan):
    for item in plan:
        for dropped in item["dropped"]:
            if (PLOTS_DIR / dropped["name"]).is_dir():
                git("rm", "-r", "-q", str(PLOTS_DIR / dropped["name"]))
        old, new = item["survivor"]["name"], item["canonical"]
        if old != new and (PLOTS_DIR / old).is_dir():
            git("mv", str(PLOTS_DIR / old), str(PLOTS_DIR / new))


def apply_data(plan, data_dir):
    root = Path(data_dir)
    parking = root / "_duplicates"
    log_lines = []

    def move(src, dst):
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        log_lines.append(f"{src}\t{dst}\n")
        print(f"    moved {src.name} -> {dst.relative_to(root)}")

    for item in plan:
        old, new = item["survivor"]["name"], item["canonical"]
        for dropped in item["dropped"]:
            src = root / dropped["name"]
            if src.is_dir() and dropped["name"] != old:
                move(src, parking / dropped["name"])
        if old != new and (root / old).is_dir():
            if (root / new).exists():
                # Leftover folder under the canonical name that no entry owns.
                move(root / new, parking / f"{new}__unowned")
            move(root / old, root / new)
    if log_lines:
        parking.mkdir(exist_ok=True)
        with open(parking / "moves.log", "a") as handle:
            handle.writelines(log_lines)


def wrangler():
    return ["wrangler"] if shutil.which("wrangler") else ["npx", "--yes", "wrangler"]


def r2_key_candidates(name):
    compact = re.sub(r"[^A-Za-z0-9]+", "", name)
    return list(
        dict.fromkeys([f"{name}.zip", f"{compact}.zip", f"{compact.lower()}.zip"])
    )


def apply_r2(plan, bucket, dry_run=False):
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        for item in plan:
            old, new = item["survivor"]["name"], item["canonical"]
            if old == new:
                continue
            local = Path(tmp) / f"{new}.zip"
            for key in r2_key_candidates(old):
                get = [
                    *wrangler(),
                    "r2",
                    "object",
                    "get",
                    f"{bucket}/{key}",
                    "--file",
                    str(local),
                    "--remote",
                ]
                if dry_run:
                    print("[dry-run] " + " ".join(get))
                    break
                if subprocess.run(get, capture_output=True).returncode == 0:
                    break
            else:
                print(f"    {old}: no FITS zip in R2; skipping")
                continue
            put = [
                *wrangler(),
                "r2",
                "object",
                "put",
                f"{bucket}/{new}.zip",
                "--file",
                str(local),
                "--remote",
            ]
            if dry_run:
                print("[dry-run] " + " ".join(put))
                continue
            subprocess.run(put, check=True, capture_output=True)
            local.unlink()
            print(f"    R2: {key} -> {new}.zip")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["plan", "apply", "r2"])
    parser.add_argument("--r2-bucket", default="lemur-fits")
    parser.add_argument("--dry-run", action="store_true", help="r2: print only")
    parser.add_argument("--sqlite-db", default=str(ROOT / "api" / "data" / "lemur.db"))
    parser.add_argument("--data-dir", default="", help="':'-separated data folders")
    parser.add_argument(
        "--only-data",
        action="store_true",
        help="apply: only move folders in --data-dir (e.g. a newly mounted drive)",
    )
    args = parser.parse_args(argv)
    data_dirs = [d for d in args.data_dir.split(":") if d]

    if args.command == "plan":
        plan = make_plan(args.sqlite_db, data_dirs)
        PLAN_PATH.write_text(json.dumps(plan, indent=2) + "\n")
        for item in plan:
            dropped = ", ".join(d["name"] for d in item["dropped"])
            print(
                f"{item['canonical']:18s} <- {item['survivor']['name']:14s} (drop {dropped})"
            )
        print(f"{len(plan)} merges written to {PLAN_PATH.relative_to(ROOT)}")
        return 0

    plan = json.loads(PLAN_PATH.read_text())
    if args.command == "r2":
        apply_r2(plan, args.r2_bucket, args.dry_run)
        return 0
    if not args.only_data:
        con = sqlite3.connect(args.sqlite_db)
        apply_db(con, plan)
        con.close()
        apply_plots(plan)
        print(f"Applied {len(plan)} merges to the DB and Web/Cluster_plots")
    for data_dir in data_dirs:
        print(f"==> Data folders in {data_dir}")
        apply_data(plan, data_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
