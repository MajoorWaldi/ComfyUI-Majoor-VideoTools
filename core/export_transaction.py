"""Cross-process export locks and durable content-addressed audio provenance."""
import os
import json
import shutil
import tempfile
import time
import wave
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

from .errors import AssemblyError
from .fingerprints import file_fingerprint, json_fingerprint


@contextmanager
def export_lock(store, key, cancelled=None, timeout=120):
    path = store.resolve("cache/export_locks/" + json_fingerprint(key) + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path))
    started = time.monotonic()
    acquired = False
    try:
        while not acquired:
            if cancelled and cancelled():
                raise AssemblyError("Cancelled while waiting for export lock")
            try:
                lock.acquire(timeout=0)
                acquired = True
            except Timeout:
                if time.monotonic() - started >= timeout:
                    raise AssemblyError("Timed out waiting for another export worker") from None
                time.sleep(.1)
        if cancelled and cancelled():
            raise AssemblyError("Cancelled before export")
        yield
    finally:
        if acquired:
            lock.release()


def durable_audio(store, path):
    if path is None:
        return None
    path = Path(path)
    fingerprint = file_fingerprint(path)
    suffix = path.suffix.lower()
    if suffix not in (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"):
        suffix = ".audio"
    relative = "sources/audio/" + fingerprint.split(":")[-1] + suffix
    destination = store.resolve(relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file() or file_fingerprint(destination) != fingerprint:
        fd, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".tmp")
        os.close(fd)
        try:
            shutil.copyfile(path, temporary)
            if file_fingerprint(Path(temporary)) != fingerprint:
                raise AssemblyError("Audio input changed while creating persistent provenance")
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
    metadata = {"version": 1, "asset_id": fingerprint, "sha256": fingerprint,
                "media_ref": relative, "rights": "user_supplied_not_verified"}
    if suffix == ".wav":
        try:
            with wave.open(str(destination), "rb") as audio:
                metadata.update(sample_rate=audio.getframerate(), channels=audio.getnchannels(),
                                duration_seconds=audio.getnframes() / audio.getframerate())
        except (wave.Error, EOFError):
            pass  # Non-PCM WAV remains identifiable by its exact content hash.
    with store.lock():
        index = store.read_json("sources/audio/index.json")
        if index is None:
            index = {"version": 1, "assets": {}}
        if not isinstance(index, dict) or index.get("version") != 1 or not isinstance(index.get("assets"), dict):
            raise AssemblyError("Invalid persistent audio index; repair it before exporting")
        index["assets"][fingerprint] = metadata
        store.write_json("sources/audio/index.json", index)
    return metadata



def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, allow_nan=False)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
