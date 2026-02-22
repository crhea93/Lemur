"""
Pipeline package bootstrap.

This keeps legacy absolute imports (e.g. ``from Misc...``) working while
allowing package-style imports (e.g. ``import Pipeline.pipeline``).
"""

import sys
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent

# Compatibility: many existing modules import siblings as top-level modules.
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))
