import os
import shutil

import pytest

from majoor_videotools.core.cache_policy import CachePolicy, cache_session, collect_cache
from majoor_videotools.core.errors import AssemblyError
from majoor_videotools.core.paths import ProjectStore


def files(tmp_path):
    store = ProjectStore(tmp_path, "p_12345678")
    old = store.resolve("cache/text/old.png")
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b"old")
    os.utime(old, (1, 1))
    recent = old.with_name("recent.png")
    recent.write_bytes(b"new")
    protected = [store.resolve(name) for name in ("sources/source.mp4", "generated/take.mp4",
                 "exports/final.mp4", "cache/audio/legacy.wav", "cache/unknown.bin")]
    for path in protected:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"keep")
        os.utime(path, (1, 1))
    return store, old, recent, protected


def test_retention_never_deletes_sources_takes_exports_or_durable_audio(tmp_path):
    store, old, recent, protected = files(tmp_path)
    report = collect_cache(store)
    assert report["removed_bytes"] == 3 and report["removed_files"] == 1
    assert not old.exists() and recent.exists()
    assert all(path.read_bytes() == b"keep" for path in protected)


def test_active_render_prevents_collection_without_serializing_other_renders(tmp_path):
    store, old, _, _ = files(tmp_path)
    with cache_session(store), cache_session(store):
        old.write_bytes(b"active")
        os.utime(old, (1, 1))
        assert collect_cache(store)["active"]
        assert old.exists()
    assert not collect_cache(store)["active"]
    assert not list(store.resolve("cache/use_locks").glob("*.lock"))


def test_referenced_intermediate_survives_retention(tmp_path):
    store, old, _, _ = files(tmp_path)
    store.write_json("manifest.json", {"source": {"uri": store.rel(old)}})
    assert collect_cache(store)["removed_files"] == 0
    assert old.exists()


def test_released_crash_lease_does_not_block_gc(tmp_path):
    store, old, _, _ = files(tmp_path)
    abandoned = store.resolve("cache/use_locks/dead.lock")
    abandoned.parent.mkdir(parents=True)
    abandoned.touch()
    assert collect_cache(store)["removed_files"] == 1
    assert not old.exists()


def test_disk_pressure_evicts_old_intermediates_but_keeps_recent_previews(tmp_path):
    store, old, recent, _ = files(tmp_path)
    report = collect_cache(store, CachePolicy(max_bytes=0, max_age_seconds=10**12))
    assert not old.exists() and recent.exists()
    assert report["remaining_bytes"] == 3 and report["warnings"]


def test_insufficient_disk_is_an_explicit_failure(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path, "p_12345678")
    monkeypatch.setattr(shutil, "disk_usage", lambda _: shutil._ntuple_diskusage(10, 10, 0))
    with pytest.raises(AssemblyError, match="free disk space"):
        with cache_session(store):
            pytest.fail("Export admitted without disk space")


@pytest.mark.parametrize("value", [-1, True, float("nan"), 1.5])
def test_invalid_cache_policy_is_rejected(value):
    with pytest.raises(ValueError):
        CachePolicy(max_bytes=value)
