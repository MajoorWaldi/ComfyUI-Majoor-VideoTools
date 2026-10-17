"""Bridge between ComfyUI VIDEO objects and plain files."""
import contextlib
import uuid
from pathlib import Path

import folder_paths
from comfy_api.latest import io

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
