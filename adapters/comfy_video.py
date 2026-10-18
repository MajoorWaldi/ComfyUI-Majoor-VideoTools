"""Bridge between ComfyUI VIDEO objects and plain files."""
import contextlib
import hashlib
import shutil
import uuid
from pathlib import Path

import folder_paths
from comfy_api.latest import io

from ..core.media_probe import probe

MajoorShotList = io.Custom("MAJOOR_SHOT_LIST")
MajoorShotMetadata = io.Custom("MAJOOR_SHOT_METADATA")

OUTPUT_SUBFOLDER = "MajoorVideoTools"


def projects_root() -> Path:
    return Path(folder_paths.get_output_directory()) / OUTPUT_SUBFOLDER


@contextlib.contextmanager
def video_file(video):
    """Yield a path holding the video. Untrimmed file-backed videos are used in place; anything else is saved first."""
    source = video.get_stream_source()
    if isinstance(source, str) and video.get_active_trim_window() == (0.0, 0.0):
        yield Path(source)
        return
    scratch = projects_root() / "_tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    tmp = scratch / f"{uuid.uuid4().hex}.mp4"
    try:
        video.save_to(str(tmp))
        yield tmp
    finally:
        tmp.unlink(missing_ok=True)


def media_ref(path: Path, kind: str, base: Path) -> dict:
    """Reference to a file under output/input/temp for the frontend widgets.

    Uses 'file'/'folder'/'kind' instead of filename/subfolder/type: ComfyUI registers entries with those keys as assets.
    """
    info = probe(path, with_packets=False)
    folder = path.parent.relative_to(base).as_posix()
    return {
        "file": path.name,
        "folder": "" if folder == "." else folder,
        "kind": kind,
        "width": info.display_size[0],
        "height": info.display_size[1],
        "fps": float(info.fps),
        "duration": float(info.duration),
    }


def preview_ref(video) -> dict:
    """Make a VIDEO viewable through /view. Files already in output/input are referenced, anything else is copied to temp."""
    with video_file(video) as path:
        path = path.resolve()
        scratch = (projects_root() / "_tmp").resolve()  # video_file deletes these on exit, so they must be copied
        for kind, folder in (("output", folder_paths.get_output_directory()), ("input", folder_paths.get_input_directory())):
            base = Path(folder).resolve()
            if path.is_relative_to(base) and not path.is_relative_to(scratch):
                break
        else:
            kind, base = "temp", Path(folder_paths.get_temp_directory()).resolve()
            stat = path.stat()
            key = hashlib.sha256(f"{path}|{stat.st_size}|{stat.st_mtime_ns}".encode()).hexdigest()[:16]
            dest = base / "majoor_compare" / f"{key}{path.suffix.lower()}"
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".partial")
                shutil.copy2(path, tmp)
                tmp.replace(dest)
            path = dest
        return media_ref(path, kind, base)
