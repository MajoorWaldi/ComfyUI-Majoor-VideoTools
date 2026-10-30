"""Collect explicit qualification inputs without importing ComfyUI or running models.

Usage: python scripts/collect_qualification.py --output PATH [--models-root PATH]
Model hashing is opt-in and never downloads files. This is an inventory, not PASS.
"""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def command(args, cwd=None):
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=15, shell=False)
        return {"returncode": result.returncode, "output": result.stdout.strip(), "error": result.stderr.strip()[-1000:]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"status": "unavailable", "error": type(error).__name__}


def collect(root, models_root=None):
    packages = {}
    for name in ("torch", "numpy", "Pillow", "scenedetect", "filelock", "av", "pytest"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    recipes = {path.relative_to(root).as_posix(): digest(path) for path in sorted((root / "workflows").glob("*.json"))}
    weights = {}
    if models_root:
        models_root = Path(models_root).resolve()
        for path in sorted(models_root.rglob("*.safetensors")):
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(models_root):
                weights[path.relative_to(models_root).as_posix()] = {"sha256": digest(path), "bytes": path.stat().st_size,
                                                                     "license_authorization": "not_verified"}
    return {"version": 1, "status": "inventory_only_not_qualification", "at_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version, "platform": platform.platform(), "packages": packages,
            "git": command(["git", "rev-parse", "HEAD"], root), "working_tree": command(["git", "status", "--porcelain"], root),
            "ffmpeg": command(["ffmpeg", "-version"]), "ffprobe": command(["ffprobe", "-version"]),
            "workflows_sha256": recipes, "models": weights, "e2e": "NOT RUN", "gpu": "NOT RUN"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models-root", type=Path)
    arguments = parser.parse_args()
    report = collect(Path(__file__).resolve().parents[1], arguments.models_root)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
