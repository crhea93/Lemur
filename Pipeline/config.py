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


def load_config(input_path):
    print("Reading Input File and Running Preliminary Steps...")
    inputs, merge_bool = read_input_file(input_path)
    env_path = inputs.get("env_file", str(Path(__file__).resolve().parent / ".env"))
    env_vars = read_env_file(env_path)
    return inputs, merge_bool, env_vars


def resolve_db_password(inputs, env_vars, default_password):
    db_password = env_vars.get("DB_PASSWORD", default_password)
    if inputs.get("database_password"):
        try:
            db_password = read_password(inputs["database_password"])
        except Exception:
            pass
    return db_password
