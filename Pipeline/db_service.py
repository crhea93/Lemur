import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from Database.Add_new import (
    add_cluster_db,
    add_coord,
    add_csb,
    add_fit_db,
    add_obsid_db,
    add_r_cool,
    get_id,
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
        sql_dump = inputs.get("sql_dump_path") or str(pipeline_dir / "Lemur_DB.sql")
        sqlite_db = inputs.get("sqlite_db_path") or str(
            repo_root / "api" / "data" / "lemur.db"
        )

        print("Updating SQL dump and API database...")
        try:
            env = dict(os.environ)
            if self.db_password:
                env["MYSQL_PWD"] = self.db_password
            dump_cmd = [
                "mysqldump",
                "--protocol=TCP",
                "-h",
                "127.0.0.1" if self.db_host == "localhost" else self.db_host,
                "-u",
                self.db_user,
                self.db_name,
            ]
            with open(sql_dump, "w", encoding="utf-8") as handle:
                subprocess.run(dump_cmd, check=True, stdout=handle, env=env)
            print(f"  Wrote SQL dump: {sql_dump}")
        except FileNotFoundError:
            print(
                "  mysqldump not found. Skipping dump; using existing SQL file if present."
            )
        except subprocess.CalledProcessError as exc:
            print(f"  mysqldump failed ({exc}). Using existing SQL file if present.")

        ingest_cmd = [
            sys.executable,
            str(repo_root / "api" / "ingest_sql_dump.py"),
            "--sql",
            sql_dump,
            "--db",
            sqlite_db,
        ]
        try:
            subprocess.run(ingest_cmd, check=True)
            print(f"  Updated SQLite DB: {sqlite_db}")
        except subprocess.CalledProcessError as exc:
            print(f"  Failed to update SQLite DB ({exc}).")

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
