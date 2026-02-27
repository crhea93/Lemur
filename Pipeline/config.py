from pathlib import Path

from Misc.read_input import read_input_file, read_password


def read_env_file(env_path):
    if not env_path or not Path(env_path).exists():
        return {}
    env = {}
    with open(env_path) as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def resolve_env_path(inputs, input_path):
    input_file_dir = Path(input_path).expanduser().parent
    repo_root = Path(__file__).resolve().parent.parent
    pipeline_dir = Path(__file__).resolve().parent

    explicit = inputs.get("env_file")
    if explicit:
        explicit_path = Path(str(explicit)).expanduser()
        if explicit_path.is_absolute():
            return str(explicit_path)
        candidate = (input_file_dir / explicit_path).resolve()
        if candidate.exists():
            return str(candidate)
        return str(explicit_path)

    for candidate in (repo_root / ".env", pipeline_dir / ".env"):
        if candidate.exists():
            return str(candidate)
    return str(repo_root / ".env")


def apply_env_defaults(inputs, env_vars):
    mapping = {
        "DB_HOST": "db_host",
        "DB_USER": "db_user",
        "DB_NAME": "db_name",
        "DB_ENGINE": "db_engine",
        "SQLITE_DB_PATH": "sqlite_db_path",
        "LEMUR_DB_PATH": "sqlite_db_path",
    }
    for env_key, input_key in mapping.items():
        if inputs.get(input_key) in (None, "") and env_vars.get(env_key):
            inputs[input_key] = env_vars[env_key]
    if not inputs.get("db_engine") and inputs.get("sqlite_db_path"):
        inputs["db_engine"] = "sqlite"
    return inputs


def load_config(input_path):
    print("Reading Input File and Running Preliminary Steps...")
    inputs, merge_bool = read_input_file(input_path)
    env_path = resolve_env_path(inputs, input_path)
    env_vars = read_env_file(env_path)
    inputs = apply_env_defaults(inputs, env_vars)
    return inputs, merge_bool, env_vars


def resolve_db_password(inputs, env_vars, default_password=None):
    db_engine = str(inputs.get("db_engine", "")).strip().lower()
    sqlite_db_path = inputs.get("sqlite_db_path")
    if not sqlite_db_path:
        sqlite_db_path = (
            Path(__file__).resolve().parent.parent / "api" / "data" / "lemur.db"
        )
    if db_engine == "sqlite" or Path(str(sqlite_db_path)).expanduser().exists():
        return ""
    db_password = env_vars.get("DB_PASSWORD", default_password or "")
    if inputs.get("database_password"):
        try:
            db_password = read_password(inputs["database_password"])
        except Exception:
            pass

    if not db_password:
        raise ValueError(
            "DB password is not configured. Set DB_PASSWORD in your env file or provide database_password in the input file."
        )

    return db_password
