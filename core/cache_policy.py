"""Bounded retention of regenerable intermediates, coordinated with exporters."""
import math
import os
import shutil
import stat
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from filelock import FileLock, Timeout

from .errors import AssemblyError


@dataclass(frozen=True)
class CachePolicy:
    max_bytes: int = 10 * 1024**3
    max_age_seconds: int = 30 * 86400
    min_free_bytes: int = 256 * 1024**2

    def __post_init__(self):
        for value in (self.max_bytes, self.max_age_seconds, self.min_free_bytes):
            if type(value) is not int or value < 0:
                raise ValueError("Cache limits must be non-negative integers")


def _regular(path):
    info = path.lstat()
    return stat.S_ISREG(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400


def _candidates(store):
    # Sources, takes, durable audio, exports and arbitrary cache files are never GC candidates.
    for relative in ("cache/text", "cache/render_sources", "cache/timeline"):
        directory = store.dir / relative
        if not directory.exists() or directory.is_symlink() or getattr(directory.lstat(), "st_file_attributes", 0) & 0x400:
            continue
        def walk_error(error):
            raise error
        for parent, directories, files in os.walk(directory, followlinks=False, onerror=walk_error):
            directories[:] = [name for name in directories
                              if not getattr((Path(parent) / name).lstat(), "st_file_attributes", 0) & 0x400
                              and not (Path(parent) / name).is_symlink()]
            for name in files:
                path = Path(parent) / name
                if path.suffix.lower() in (".png", ".wav", ".mp4") and _regular(path):
                    yield path
    for path in store.resolve("cache").glob("sfx_*.wav"):
        if _regular(path):
            yield path


def _active_leases(store):
    directory = store.resolve("cache/use_locks")
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob("*.lock"):
        lock = FileLock(str(path))
        try:
            lock.acquire(timeout=0)
        except Timeout:
            return True
        else:
            lock.release()
    return False


def _collect_locked(store, policy, now):
    result = {"removed_bytes": 0, "removed_files": 0, "active": False, "warnings": []}
    if _active_leases(store):
        result["active"] = True
        return result
    retained = set()
    def references(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("uri", "media_ref", "source_media_ref", "thumbnail_ref", "file") and isinstance(item, str):
                    retained.add(store.resolve(item))
                else:
                    references(item)
        elif isinstance(value, list):
            for item in value:
                references(item)
    for relative in ("manifest.json", "editor/timeline.json", "sources/audio/index.json"):
        references(store.read_json(relative))
    paths = sorted(((path, path.stat()) for path in _candidates(store) if path not in retained),
                   key=lambda row: row[1].st_mtime)
    total = sum(info.st_size for _, info in paths)
    free = shutil.disk_usage(store.dir).free
    for path, info in paths:
        expired = now - info.st_mtime >= policy.max_age_seconds
        # A grace period prevents eviction of newly served previews between requests.
        pressure = (total > policy.max_bytes or free < policy.min_free_bytes) and now - info.st_mtime >= 3600
        if not expired and not pressure:
            continue
        try:
            if not _regular(path):
                raise OSError("Cache candidate changed to a non-regular file")
            path.unlink()
        except OSError as error:
            result["warnings"].append(f"Cache retention could not remove {store.rel(path)}: {error}")
        else:
            total -= info.st_size
            free += info.st_size
            result["removed_files"] += 1
            result["removed_bytes"] += info.st_size
    result["remaining_bytes"] = total
    if total > policy.max_bytes:
        result["warnings"].append("Regenerable cache exceeds its budget; recent or in-use files were retained.")
    return result


def collect_cache(store, policy=CachePolicy(), *, now=None):
    now = time.time() if now is None else now
    if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now):
        raise ValueError("Cache collection time must be finite")
    with FileLock(str(store.resolve("cache/.maintenance.lock")), timeout=120):
        return _collect_locked(store, policy, now)


@contextmanager
def cache_session(store, policy=CachePolicy()):
    maintenance = FileLock(str(store.resolve("cache/.maintenance.lock")), timeout=120)
    with maintenance:
        report = _collect_locked(store, policy, time.time())
        free = shutil.disk_usage(store.dir).free
        if free < policy.min_free_bytes:
            raise AssemblyError(f"Not enough free disk space for export ({free:,} bytes free; "
                                f"{policy.min_free_bytes:,} required). Free space and retry.")
        path = store.resolve(f"cache/use_locks/{uuid.uuid4().hex}.lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        lease = FileLock(str(path))
        lease.acquire(timeout=0)
    try:
        yield report["warnings"]
    finally:
        with maintenance:
            lease.release()
            path.unlink(missing_ok=True)
