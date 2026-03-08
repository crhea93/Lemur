# Contributing

## Development setup
1. Create/activate a virtual environment.
2. Install dependencies:
```bash
pip install -e ".[dev]"
```
3. Install git hooks:
```bash
pre-commit install
```

You can run hooks manually at any time:
```bash
pre-commit run --all-files
```

## Local checks before opening a PR
Run all checks from repo root:
```bash
ruff check tests api/app.py api/ingest_sql_dump.py Pipeline/config.py
black --check tests api/app.py api/ingest_sql_dump.py Pipeline/config.py
mypy api Pipeline/config.py Pipeline/pipeline.py tests
pytest --junitxml=pytest.xml --cov=api --cov=Pipeline.config --cov=Pipeline.pipeline --cov-report=term-missing --cov-report=xml
```

## Pull request checklist
1. Keep changes focused and atomic.
2. Add or update tests for behavior changes.
3. Update docs (`README.md` and relevant module docs) when behavior changes.
4. Ensure CI passes.

## Branching
- Open PRs against `master` unless coordinating a release/maintenance branch change.
