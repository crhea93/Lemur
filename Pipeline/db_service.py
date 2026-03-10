import shutil
import subprocess
import urllib.request
from pathlib import Path

from Database.Add_new import (
    add_cluster_db,
    add_coord,
    add_csb,
    add_fit_db,
    add_obsid_db,
    add_r_cool,
    get_center,
    get_double_beta_fit,
    get_id,
    upsert_center,
    upsert_double_beta_fit,
)


class DatabaseService:
    def __init__(self, mydb, mycursor, db_user, db_password, db_host, db_name):
        self.mydb = mydb
        self.mycursor = mycursor
        self.db_user = db_user
        self.db_password = db_password
        self.db_host = db_host
        self.db_name = db_name

    def add_cluster(self, cluster_name, redshift):
        return add_cluster_db(self.mydb, self.mycursor, cluster_name, redshift)

    def add_obsid(self, cluster_name, obsid):
        return add_obsid_db(self.mydb, self.mycursor, cluster_name, obsid)

    def add_coord(self, cluster_name, ra, dec):
        return add_coord(self.mydb, self.mycursor, cluster_name, ra, dec)

    def upsert_center(self, cluster_name, *args, **kwargs):
        return upsert_center(
            self.mydb, self.mycursor, cluster_name, *args, **kwargs
        )

    def get_center(self, cluster_name):
        return get_center(self.mydb, self.mycursor, cluster_name)

    def upsert_double_beta_fit(self, cluster_name, *args, **kwargs):
        return upsert_double_beta_fit(
            self.mydb, self.mycursor, cluster_name, *args, **kwargs
        )

    def get_double_beta_fit(self, cluster_name):
        return get_double_beta_fit(self.mydb, self.mycursor, cluster_name)

    def add_r_cool(self, cluster_id, cluster_name, *args, **kwargs):
        return add_r_cool(
            self.mydb, self.mycursor, cluster_id, cluster_name, *args, **kwargs
        )

    def add_csb(self, cluster_id, cluster_name, *args, **kwargs):
        return add_csb(
            self.mydb, self.mycursor, cluster_id, cluster_name, *args, **kwargs
        )

    def add_fit(self, *args, **kwargs):
        return add_fit_db(self.mydb, self.mycursor, *args, **kwargs)

    def get_id(self, cluster_name):
        return get_id(self.mydb, self.mycursor, cluster_name)

    def update_api_db(self, inputs):
        update_api = str(inputs.get("update_api", "false")).lower() == "true"
        if not update_api:
            return

        pipeline_dir = Path(__file__).resolve().parent
        repo_root = pipeline_dir.parent
        sqlite_db = inputs.get("sqlite_db_path") or str(
            repo_root / "api" / "data" / "lemur.db"
        )

        source_sqlite = inputs.get("sqlite_db_path") or sqlite_db
        source_path = Path(source_sqlite)
        target_path = Path(sqlite_db)
        if not source_path.exists():
            print(f"  SQLite source DB missing: {source_path}")
        elif source_path.resolve() != target_path.resolve():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            print(f"  Copied SQLite DB: {source_path} -> {target_path}")
        else:
            print(f"  SQLite DB already current: {target_path}")

        self.restart_api_if_running(inputs)

    def restart_api_if_running(self, inputs):
        restart_api = str(inputs.get("api_restart", "false")).lower() == "true"
        if not restart_api:
            return

        health_url = inputs.get("api_health_url", "http://localhost:8000/api/health")
        try:
            with urllib.request.urlopen(health_url, timeout=2) as resp:
                if resp.status != 200:
                    print("  API health check failed; skipping restart.")
                    return
        except Exception:
            print("  API not reachable; skipping restart.")
            return

        restart_cmd = inputs.get("api_restart_cmd")
        if not restart_cmd:
            print(
                "  api_restart is true but api_restart_cmd is not set; skipping restart."
            )
            return

        print("  Restarting API...")
        try:
            subprocess.run(restart_cmd, check=True, shell=True)
        except subprocess.CalledProcessError as exc:
            print(f"  API restart failed ({exc}).")
