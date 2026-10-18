import hashlib
import json
from pathlib import Path

CHUNK = 8 * 1024 * 1024


def file_fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def json_fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def short(fingerprint: str, n: int = 8) -> str:
    return fingerprint.split(":")[-1][:n]
