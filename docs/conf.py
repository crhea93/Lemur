from __future__ import annotations

from pathlib import Path

project = "Lemur"
author = "Lemur Contributors"
copyright = "2026, Lemur Contributors"

extensions: list[str] = []
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

# Keep source links stable when built locally.
root_doc = "index"

# Optional metadata for generated docs.
html_title = "Lemur Documentation"
html_short_title = "Lemur Docs"
