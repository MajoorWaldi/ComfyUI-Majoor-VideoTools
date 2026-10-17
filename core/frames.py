"""Frame extraction through ffmpeg: handles rotation, VFR and exact seeking in one place."""
from fractions import Fraction
from pathlib import Path

import numpy as np

from ..adapters.ffmpeg import run_capture
from .media_probe import MediaInfo
from .models import Shot, Source
from .timeline import frame_time


def _seek_args(t: Fraction, frame_duration: Fraction) -> list[str]:
    # Seek a quarter frame early: ffmpeg keeps the first frame whose pts >= ss.
    return ["-ss", f"{max(float(t - frame_duration / 4), 0.0):.6f}"]


def _scaled_size(info_size: tuple[int, int], max_side: int) -> tuple[int, int]:
    w, h = info_size
    scale = min(1.0, max_side / max(w, h))
    return max(2, int(round(w * scale / 2)) * 2), max(2, int(round(h * scale / 2)) * 2)


def extract_frame(path: Path, t: Fraction, frame_duration: Fraction, display_size: tuple[int, int], max_side: int) -> np.ndarray:
    """Decode one RGB frame [H, W, 3] uint8 at time t, scaled so the longest side is <= max_side."""
    w, h = _scaled_size(display_size, max_side)
    raw = run_capture(
        ["-v", "error", *_seek_args(t, frame_duration), "-i", str(path), "-frames:v", "1", "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    )
    if len(raw) != w * h * 3:
        raise ValueError(f"No frame could be decoded at {float(t):.3f}s from {path.name}")
    return np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3).copy()


def sample_indices(mode: str, count: int, frame_count: int) -> list[int]:
    last = frame_count - 1
    if mode == "first":
        return [0]
    if mode == "last":
        return [last]
    if mode == "middle":
        return [last // 2]
    if mode == "first_middle_last":
        return sorted({0, last // 2, last})
    count = max(1, min(count, frame_count))
    if count == 1:
        return [last // 2]
    return sorted({round(i * last / (count - 1)) for i in range(count)})


def sample_original_shot(path: Path, source: Source, shot: Shot, mode: str, count: int, max_side: int) -> np.ndarray:
    fd = 1 / source.fps
    frames = [
        extract_frame(path, frame_time(source, shot, k), fd, (source.width, source.height), max_side)
        for k in sample_indices(mode, count, shot.frame_count)
    ]
    return np.stack(frames)


def sample_whole_media(path: Path, info: MediaInfo, mode: str, count: int, max_side: int) -> np.ndarray:
    fd = 1 / info.fps
    n = max(1, round(info.duration * info.fps))
    frames = [extract_frame(path, k * fd, fd, info.display_size, max_side) for k in sample_indices(mode, count, n)]
    return np.stack(frames)


def write_thumbnail(path: Path, t: Fraction, frame_duration: Fraction, out: Path, height: int = 180) -> None:
    tmp = out.with_suffix(".partial.jpg")
    run_capture(["-v", "error", "-y", *_seek_args(t, frame_duration), "-i", str(path), "-frames:v", "1", "-vf", f"scale=-2:{height}", str(tmp)])
    tmp.replace(out)
