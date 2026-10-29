import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock

from .errors import PathError

SUBDIRS = ("sources", "cache/scene_metrics", "cache/thumbnails", "cache/clips", "generated", "exports", "manifests", "logs")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_name(name: str, default: str = "majoor_edit") -> str:
    name = _SAFE_NAME.sub("_", name.strip()).strip("._")
    return name[:80] or default


class ProjectStore:
    """Owns one project directory. Every path handed out is checked to stay inside it."""

    def __init__(self, root: Path, project_id: str):
        if not re.fullmatch(r"p_[0-9a-f]{8,32}", project_id):
            raise PathError(f"Invalid project id '{project_id}'")
        root = Path(root).resolve()
        self.dir = (root / project_id).resolve()
        if self.dir.parent != root:
            raise PathError(f"Project '{project_id}' escapes the output directory")
        for sub in SUBDIRS:
            (self.dir / sub).mkdir(parents=True, exist_ok=True)

    def resolve(self, rel: str) -> Path:
        path = (self.dir / rel).resolve()
        if not path.is_relative_to(self.dir):
            raise PathError(f"Path '{rel}' escapes the project directory")
        return path

    def rel(self, path: Path) -> str:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(self.dir):
            raise PathError(f"Path '{path}' is outside the project directory")
        return resolved.relative_to(self.dir).as_posix()

    @contextmanager
    def lock(self):
        with FileLock(str(self.dir / ".lock"), timeout=120):
            yield

    def write_json(self, rel: str, data: dict) -> Path:
        """Write atomically so a crash never leaves a truncated manifest."""
        path = self.resolve(rel)
        path.parent.mkdir(parents=True,exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            for attempt in range(6):
                try:
                    os.replace(tmp, path)
                    break
                except PermissionError:
                    if os.name != 'nt' or attempt == 5:
                        raise
                    time.sleep(.01 * 2**attempt)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return path

    def read_json(self, rel: str) -> dict | None:
        path = self.resolve(rel)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
