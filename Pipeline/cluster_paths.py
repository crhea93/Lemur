"""Locate a cluster's data folder when its name and folder name differ.

Database names and folder names on the data drive drift apart (e.g.
``Abell2052`` vs ``A2052``, ``Perseuscluster`` vs ``PerseusCluster``). Names are
compared after normalization; among matching folders that contain the
requested file, the most recently written one wins.

``home_dir`` may list several data folders separated by ``os.pathsep`` (``:``
on Linux/macOS), e.g. two drives; they are searched in order.
"""

import os
import re
from functools import lru_cache
from pathlib import Path

IMAGE_NAME = "broad_flux.img"


def normalize_cluster_name(name):
    text = re.sub(r"[^a-z0-9]", "", str(name or "").lower())
    # Abell catalog prefixes: Abell2052 / ABELL2052 / ACO2052 / A02052 -> a2052
    text = re.sub(r"^(abell|aco)(?=\d)", "a", text)
    return re.sub(r"^a0+(?=\d)", "a", text)


@lru_cache(maxsize=8)
def _folders_by_normalized_name(home_dir):
    index: dict[str, list[Path]] = {}
    root = Path(home_dir)
    if root.is_dir():
        for child in root.iterdir():
            if child.is_dir() and not child.name.isdigit():
                index.setdefault(normalize_cluster_name(child.name), []).append(child)
    return index


def data_roots(home_dir):
    return [Path(p) for p in str(home_dir or "").split(os.pathsep) if p]


def resolve_cluster_file(home_dir, name, filename=IMAGE_NAME):
    """Return the path to ``<cluster folder>/<filename>``, or None.

    Exact folder names win over normalized matches, and earlier roots win over
    later ones.
    """
    roots = data_roots(home_dir)
    for root in roots:
        exact = root / name / filename
        if exact.exists():
            return exact
    for root in roots:
        candidates = [
            folder / filename
            for folder in _folders_by_normalized_name(str(root)).get(
                normalize_cluster_name(name), []
            )
            if (folder / filename).exists()
        ]
        if candidates:
            # Same normalized name means the same object processed more than
            # once (e.g. Abell2319 and ABELL2319); use the newest image.
            return max(candidates, key=lambda path: path.stat().st_mtime)
    return None
