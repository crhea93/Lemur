from Pipeline import cluster_paths as cp


def _make(root, folder, with_image=True):
    path = root / folder
    path.mkdir()
    if with_image:
        (path / cp.IMAGE_NAME).write_bytes(b"")
    return path / cp.IMAGE_NAME


def test_normalize_cluster_name_unifies_abell_prefixes():
    names = ["Abell2052", "ABELL2052", "ACO2052", "A2052", "A02052", "abell 2052"]
    assert {cp.normalize_cluster_name(n) for n in names} == {"a2052"}
    assert cp.normalize_cluster_name("Perseus cluster") == "perseuscluster"
    assert cp.normalize_cluster_name("A2052") != cp.normalize_cluster_name("A205")


def test_resolve_prefers_exact_then_alias(tmp_path):
    exact = _make(tmp_path, "Abell133")
    alias = _make(tmp_path, "A2052")
    cp._folders_by_normalized_name.cache_clear()
    assert cp.resolve_cluster_file(tmp_path, "Abell133") == exact
    assert cp.resolve_cluster_file(tmp_path, "Abell2052") == alias
    assert cp.resolve_cluster_file(tmp_path, "Perseuscluster") is None


def test_resolve_skips_folders_without_image_and_prefers_newest(tmp_path):
    import os

    _make(tmp_path, "ABELL1835", with_image=False)
    older = _make(tmp_path, "A754")
    newer = _make(tmp_path, "ABELL754")
    os.utime(older, (1_000, 1_000))
    os.utime(newer, (2_000, 2_000))
    (tmp_path / "12345").mkdir()  # ObsID folders are ignored
    cp._folders_by_normalized_name.cache_clear()
    assert cp.resolve_cluster_file(tmp_path, "Abell1835") is None
    assert cp.resolve_cluster_file(tmp_path, "Abell754") == newer


def test_resolve_searches_multiple_roots_in_order(tmp_path):
    first, second = tmp_path / "drive1", tmp_path / "drive2"
    first.mkdir()
    second.mkdir()
    in_first = _make(first, "Abell133")
    _make(second, "Abell133")
    only_second = _make(second, "A2199")
    cp._folders_by_normalized_name.cache_clear()
    home = f"{first}:{second}"
    assert cp.resolve_cluster_file(home, "Abell133") == in_first
    assert cp.resolve_cluster_file(home, "Abell2199") == only_second
