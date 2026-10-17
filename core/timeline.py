"""Exact time arithmetic. Frames/PTS are authoritative; floats are for display only."""
from bisect import bisect_left
from fractions import Fraction

from .models import Shot, Source


def shot_start(source: Source, shot: Shot) -> Fraction:
    """Seconds from the first frame of the source to the first frame of the shot."""
    if shot.start_pts is not None:
        return (shot.start_pts - source.first_pts) * source.time_base
    return shot.start_frame / source.fps


def shot_duration(source: Source, shot: Shot) -> Fraction:
    if shot.start_pts is not None and shot.end_pts_exclusive is not None:
        return (shot.end_pts_exclusive - shot.start_pts) * source.time_base
    return shot.frame_count / source.fps


def frame_time(source: Source, shot: Shot, k: int) -> Fraction:
    """Time of the k-th frame of a shot (exact for CFR, interpolated for VFR)."""
    if source.timing_mode == "CFR" or shot.frame_count <= 1:
        return shot_start(source, shot) + k / source.fps
    span = shot_duration(source, shot) - 1 / source.fps
    return shot_start(source, shot) + span * k / (shot.frame_count - 1)


def nearest_frame_index(pts: list[int], target_pts: float) -> int:
    i = bisect_left(pts, target_pts)
    if i == 0:
        return 0
    if i == len(pts):
        return len(pts) - 1
    return i if pts[i] - target_pts < target_pts - pts[i - 1] else i - 1


def format_timecode(seconds: float) -> str:
    minutes, secs = divmod(seconds, 60)
    return f"{int(minutes):02d}:{secs:04.1f}"
