"""The motion of a generated take against the music under its shot: where the take moves most (its motion peaks) and which start in the take
puts those peaks on the attacks of the music. Measured on small gray frames (energy.read_gray), no model.

A generated take is calmer than footage and its peaks are less clear (MV-Crafter, arXiv 2504.17267); matching motion peaks to beats in
order is the idea of MVAA (arXiv 2506.18881), here only by choosing where the take starts, never by redrawing frames."""
import math

import numpy as np

SPREAD = 0.06       # seconds: how far a motion peak may sit from an attack and still count as on it
MAX_SLIP = 0.5      # seconds: the take never starts later than this, so the action it was asked for stays in the shot
SHORT_CUT = 22      # frames: a cut shorter than this was generated longer (H3's minimum), so any part of that take may be shown
MIN_GAIN = 0.25     # a later start must line up this much more attack weight than the start of the take, or the take keeps its start


def motion_curve(frames: np.ndarray) -> np.ndarray:
    """How much the picture changes at each frame (mean difference of 255 from the frame before), lightly smoothed."""
    if len(frames) < 2:
        return np.zeros(len(frames))
    raw = np.r_[0.0, [float(np.abs(frames[i].astype(np.int16) - frames[i - 1].astype(np.int16)).mean()) for i in range(1, len(frames))]]
    return np.convolve(raw, [.25, .5, .25], mode="same")


def motion_peaks(curve: np.ndarray) -> list[tuple[int, float]]:
    """(frame, height 0..1) of the moments the picture moves most: local maxima clearly above the usual motion of the take."""
    if len(curve) < 3 or curve.max() <= 0:
        return []
    floor = float(np.median(curve)) + max(.5, .5 * float(np.std(curve)))
    top = float(curve.max())
    return [(i, float(curve[i]) / top) for i in range(1, len(curve) - 1)
            if curve[i] >= curve[i - 1] and curve[i] > curve[i + 1] and curve[i] >= floor]


def alignment(peaks, accents, fps: float, slip: int, length: int) -> float:
    """How much attack weight the motion peaks inside [slip, slip + length) put on the attacks: each attack (seconds from the start of the shot,
    strength) counts its strength times the height of the closest peak, discounted by their distance."""
    inside = [(f - slip, h) for f, h in peaks if slip <= f < slip + length]
    score = 0.0
    for at, strength in accents:
        if inside:
            score += strength * max(h * math.exp(-((f / fps - at) ** 2) / (2 * SPREAD ** 2)) for f, h in inside)
    return score


def best_slip(frames: np.ndarray, fps: float, accents, needed: int) -> tuple[int, float, float]:
    """(frames to skip at the start of the take, score of that start, score of the take as it is). The take keeps its start unless a later
    one, at most MAX_SLIP seconds in and leaving `needed` frames, lines up clearly more attack weight."""
    peaks = motion_peaks(motion_curve(frames))
    if not peaks or not accents:
        return 0, 0.0, 0.0
    base = alignment(peaks, accents, fps, 0, needed)
    best, score = 0, base
    reach = len(frames) - needed if needed < SHORT_CUT else round(MAX_SLIP * fps)  # the judge's pick: the window of a short cut is free inside its longer take
    for slip in range(1, min(reach, len(frames) - needed) + 1):
        value = alignment(peaks, accents, fps, slip, needed)
        if value > score + 1e-9:
            best, score = slip, value
    return (best, score, base) if score >= base + MIN_GAIN else (0, base, base)


DRIFT_MIN = 0.6  # pixels (of 160) per frame: under this a take does not travel enough to give a whip its way


def take_drift(path, start: float = 0.0, frames: int = 6) -> tuple[float, float]:
    """How the picture of a take travels over its first `frames` frames from `start`: the mean shift per frame, in pixels of 160 (right and down positive)."""
    from fractions import Fraction

    from . import energy

    gray = energy.read_gray(path, Fraction(24), limit=frames + 1, start=start)
    shifts = [energy.global_motion(gray[i - 1], gray[i])[:2] for i in range(1, len(gray))]
    if not shifts:
        return 0.0, 0.0
    return float(np.mean([s[0] for s in shifts])), float(np.mean([s[1] for s in shifts]))


def whip_direction(dx: float, dy: float) -> str | None:
    """The way a whip into a take should travel so that the cut carries on the motion of the take: its main axis and sign, or None for a still take."""
    if max(abs(dx), abs(dy)) < DRIFT_MIN:
        return None
    if abs(dx) >= abs(dy):
        return "right" if dx > 0 else "left"
    return "down" if dy > 0 else "up"
