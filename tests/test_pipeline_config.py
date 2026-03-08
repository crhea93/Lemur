from Pipeline import config


def test_read_env_file_parses_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
# comment
DB_PASSWORD="secret value"
FOO='bar'
EMPTY=
INVALID_LINE
""".strip()
        + "\n",
        encoding="utf-8",
    )

    parsed = config.read_env_file(str(env_file))

    assert parsed["DB_PASSWORD"] == "secret value"
    assert parsed["FOO"] == "bar"
    assert parsed["EMPTY"] == ""
    assert "INVALID_LINE" not in parsed


def test_read_env_file_missing_file_returns_empty_dict(tmp_path):
    missing = tmp_path / "does-not-exist.env"
    assert config.read_env_file(str(missing)) == {}


def test_load_config_uses_env_file_from_inputs(monkeypatch, tmp_path):
    env_file = tmp_path / "custom.env"
    env_file.write_text("DB_PASSWORD=from_env_file\n", encoding="utf-8")

    def fake_read_input_file(_):
        return ({"env_file": str(env_file)}, False)

    monkeypatch.setattr(config, "read_input_file", fake_read_input_file)

    inputs, merge_bool, env_vars = config.load_config("ignored.i")

    assert inputs["env_file"] == str(env_file)
    assert merge_bool is False
    assert env_vars["DB_PASSWORD"] == "from_env_file"


def test_resolve_env_path_prefers_repo_root_env(monkeypatch, tmp_path):
    fake_config = tmp_path / "repo" / "Pipeline" / "config.py"
    fake_config.parent.mkdir(parents=True)
    fake_config.write_text("# stub\n", encoding="utf-8")
    (fake_config.parent.parent / ".env").write_text(
        "DB_PASSWORD=repo\n", encoding="utf-8"
    )
    (fake_config.parent / ".env").write_text("DB_PASSWORD=pipeline\n", encoding="utf-8")

    monkeypatch.setattr(config, "__file__", str(fake_config))
    resolved = config.resolve_env_path({}, str(tmp_path / "inputs" / "template.i"))
    assert resolved == str(fake_config.parent.parent / ".env")


def test_load_config_applies_env_defaults(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DB_ENGINE=sqlite\nLEMUR_DB_PATH=/tmp/lemur.db\nDB_NAME=Lemur_DB\n",
        encoding="utf-8",
    )

    def fake_read_input_file(_):
        return ({"env_file": str(env_file)}, False)

    monkeypatch.setattr(config, "read_input_file", fake_read_input_file)
    inputs, _merge_bool, _env_vars = config.load_config("ignored.i")
    assert inputs["db_engine"] == "sqlite"
    assert inputs["sqlite_db_path"] == "/tmp/lemur.db"
    assert inputs["db_name"] == "Lemur_DB"


def test_resolve_db_password_prefers_database_password_file(monkeypatch):
    monkeypatch.setattr(config, "read_password", lambda _: "from_password_file")

    resolved = config.resolve_db_password(
        {"database_password": "/tmp/password.txt"},
        {"DB_PASSWORD": "from_env"},
    )

    assert resolved == "from_password_file"


def test_resolve_db_password_falls_back_to_env():
    resolved = config.resolve_db_password({}, {"DB_PASSWORD": "from_env"})
    assert resolved == "from_env"


def test_resolve_db_password_uses_default_when_env_missing():
    resolved = config.resolve_db_password({}, {}, default_password="fallback")
    assert resolved == "fallback"


def test_resolve_db_password_not_required_for_sqlite():
    assert config.resolve_db_password({"db_engine": "sqlite"}, {}) == ""
