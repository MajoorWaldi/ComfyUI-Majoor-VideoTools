"""Cut Markers: cuts placed by hand on a timeline (with the waveform of a music, the cuts of a video, the beats) become a rhythm skeleton.

The markers are plain seconds in a text widget; the editor in web/majoor_cuts.js reads and writes the same text."""
import re

import numpy as np

from .errors import MajoorError
from .fx import SUB_MIN_FRAMES
from .scene_detection import merge_short_shots
from .template import MIN_SHOT_FRAMES
from .timeline_sources import group_cuts

PEAKS = 1600  # points of the waveform sent to the editor


def _seconds(token: str, fps: float) -> float:
    t = token.strip().lower()
    if t.endswith("f") and t[:-1].replace(".", "", 1).isdigit():
        return float(t[:-1]) / fps  # 36f
    if t.endswith("s"):
        t = t[:-1]
    parts = t.split(":")
    if len(parts) > 3:
        raise ValueError(token)
    total = 0.0
    for part in parts:  # 12.5, 1:02.5, 0:1:02
        total = total * 60 + float(part)
    return total


def parse_markers(text: str, fps: float = 24.0) -> list[float]:
    """Seconds ('12.5', '12.5s'), timecodes ('1:02.5') or frames ('36f') separated by commas, spaces or new lines -> sorted unique seconds."""
    found: set[float] = set()
    for token in re.split(r"[,;\s]+", (text or "").strip()):
        if not token:
            continue
        try:
            found.add(round(_seconds(token, fps), 4))
        except ValueError:
            raise MajoorError(f"Cannot read the marker '{token}': use seconds (12.5), a timecode (1:02.5) or frames (36f)") from None
    return sorted(t for t in found if t > 0)


def format_markers(times: list[float]) -> str:
    return " ".join(f"{t:.3f}".rstrip("0").rstrip(".") for t in sorted(times))


def plan_from_markers(markers: list[float], total_seconds: float, *, fps: float = 24.0, min_shot_seconds: float = 1.0, aspect_ratio: str | None = None) -> tuple[dict, dict]:
    """Shots between the markers; cuts shorter than min_shot_seconds in a row are grouped into one shot whose cuts become its sub-cuts. Returns (plan, info)."""
    if total_seconds <= 0:
        raise MajoorError("Cut Markers needs a duration: connect a video or a music, or set duration")
    total = max(round(total_seconds * fps), 1)
    warnings: list[str] = []
    inside = sorted({round(t * fps) for t in markers} - {0})
    dropped = [f for f in inside if f >= total]
    if dropped:
        warnings.append(f"{len(dropped)} marker(s) after the end ({total_seconds:.2f} s) ignored")
    cuts = merge_short_shots([f for f in inside if f < total], total, SUB_MIN_FRAMES, warnings)
    bounds = [0, *cuts, total]
    lengths = [b - a for a, b in zip(bounds, bounds[1:])]
    groups = group_cuts(lengths, max(round(min_shot_seconds * fps), MIN_SHOT_FRAMES))
    rows, at = [], 0
    for group in groups:
        row = {"duration_frames": sum(group), "prompt": "", "notes": f"markers {at / fps:.2f}-{(at + sum(group)) / fps:.2f}s, {len(group)} cut{'s' if len(group) > 1 else ''}"}
        if len(group) > 1:
            row["sub_cuts"] = [{"duration_frames": n} for n in group]
        rows.append(row)
        at += sum(group)
    plan: dict = {"fps": fps, "shots": rows}
    if aspect_ratio:
        plan["aspect_ratio"] = aspect_ratio
    return plan, {"cuts": len(lengths), "shots": len(rows), "warnings": warnings}


def waveform_peaks(samples: np.ndarray, count: int = PEAKS) -> list[float]:
    """Loudness of `count` equal slices of a mono waveform, 0..1, rounded for the browser."""
    if len(samples) == 0:
        return []
    count = min(count, len(samples))
    edges = np.linspace(0, len(samples), count + 1).astype(int)
    peaks = np.array([np.abs(samples[a:b]).max() if b > a else 0.0 for a, b in zip(edges, edges[1:])], dtype=np.float32)
    top = float(peaks.max())
    return [round(float(p) / top, 3) for p in peaks] if top > 0 else [0.0] * len(peaks)


def extend_beats(beats: np.ndarray, bpm: float, duration: float) -> np.ndarray:
    """The beats of a music that is shorter than the edit go on at the same tempo until `duration`."""
    if len(beats) == 0 or bpm <= 0:
        return beats
    period = 60.0 / bpm
    steps = int((duration - float(beats[-1])) // period)
    return np.concatenate([beats, float(beats[-1]) + period * np.arange(1, steps + 1)]) if steps > 0 else beats


def beat_grid(beats: np.ndarray, duration: float) -> list[float]:
    return [round(float(t), 4) for t in beats if 0 <= t <= duration]


def preview_mono(samples: np.ndarray, rate: int, target_rate: int = 22050) -> tuple[np.ndarray, int]:
    """A lighter copy of the music for the browser: mono, about 22 kHz, by averaging whole groups of samples."""
    step = max(rate // target_rate, 1)
    usable = len(samples) - len(samples) % step
    if step > 1 and usable:
        samples = samples[:usable].reshape(-1, step).mean(axis=1)
    return samples.astype(np.float32), rate // step
