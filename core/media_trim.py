"""Frame-accurate extraction of an original shot into a standalone clip."""
from fractions import Fraction
from pathlib import Path

from ..adapters.ffmpeg import run_ffmpeg
from .fingerprints import short
from .models import Shot, Source
from .paths import ProjectStore
from .timeline import shot_duration, shot_start

CLIP_VERSION = "v1"


def segment_args(source: Source, shot: Shot) -> tuple[list[str], int]:
    """Input options selecting exactly the frames of a shot, plus its frame count.

    Seeking half a frame early and limiting by duration keeps the first frame (pts >= ss) and drops the next
    shot's first frame; -frames:v at the output is the final guard.
    """
    fd = 1 / source.fps
    start = shot_start(source, shot)
    ss = max(start - fd / 2, Fraction(0))
    return ["-ss", f"{float(ss):.6f}", "-t", f"{float(shot_duration(source, shot) + (start - ss)):.6f}"], shot.frame_count


def clip_path(store: ProjectStore, source: Source, shot: Shot) -> Path:
    name = f"{shot.shot_id}_{short(source.fingerprint)}_{shot.start_frame}-{shot.end_frame_exclusive}_{CLIP_VERSION}.mp4"
    return store.resolve(f"cache/clips/{name}")


def materialize_clip(store: ProjectStore, source: Source, shot: Shot) -> Path:
    out = clip_path(store, source, shot)
    if out.exists():
        return out
    seg, frames = segment_args(source, shot)
    tmp = out.with_name(out.stem + ".partial.mp4")
    run_ffmpeg(
        [
            "-y", *seg, "-i", str(store.resolve(source.uri)),
            "-map", "0:v:0", "-map", "0:a:0?",
            "-frames:v", str(frames), "-fps_mode", "passthrough",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-crf", "12", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-map_metadata", "-1",
            str(tmp),
        ]
    )
    tmp.replace(out)
    return out
