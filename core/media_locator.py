"""Output-relative ComfyUI media locations; never expose absolute server paths."""
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from .errors import PathError


def output_location(path: Path, output_root: Path) -> str:
    base = Path(output_root).resolve()
    target = Path(path).resolve()
    if not target.is_relative_to(base) or target == base:
        raise PathError("Media is outside ComfyUI output; remote artifact transfer is required")
    # Resolve catches symlink escapes. URLs remain relative to ComfyUI output.
    return target.relative_to(base).as_posix()


def project_media_location(storage_root: Path, project_id: str, output_root: Path, relative: str = "") -> str:
    import re
    if not re.fullmatch(r"p_[0-9a-f]{8,32}", project_id):
        raise PathError("Invalid media project id")
    value = str(relative).replace("\\", "/")
    decoded = unquote(value)
    if decoded != value or PurePosixPath(value).is_absolute() or ":" in value or any(part in (".", "..") for part in value.split("/")):
        raise PathError("Invalid project-relative media path")
    root = Path(storage_root).resolve()
    project = root / project_id
    if project.is_symlink() or project.resolve().parent != root:
        raise PathError("Media project escapes its storage root")
    target = (project / value).resolve()
    if not target.is_relative_to(project.resolve()):
        raise PathError("Media escapes its project")
    return output_location(target, output_root)
