"""The energy of an edit, measured: flashes, shakes, punch-ins, whips and camera moves of a video, frame by frame.

A generated take comes back calmer than the footage it replaces: the flashes, the shake bursts and the punch-ins of the original are lost. This module measures them on the
original (a small gray copy of every frame: the luma, and the global motion between two frames: a translation and a scale), cleans the cuts of what a flash
makes of them, and writes what a shot did as the effects of a plan row (a transition into the shot, sub-cuts with a transition at each event, a push-in), which
Shot Assemble applies to the generated take."""
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

from .errors import MajoorError

SIZE = (160, 90)
FLASH_RISE = 28.0       # luma above the surroundings, on a scale of 255
FLASH_BACK = 12.0       # luma of the frame after the flash, still above the surroundings at most this much
FLASH_MAX = 4           # frames
SHAKE_STEP = 2.6        # pixels (of 160) between two frames of a shake, the direction changing
SHAKE_MIN = 4           # frames
WHIP_STEP = 36.0        # pixels (of 160) in one frame
PUNCH_STEP = 0.03       # scale change in one frame
PUSH_STEP = 0.003       # scale change per frame, kept for PUSH_MIN frames
PUSH_MIN = 8
SAME_SHOT = 14.0        # mean difference (of 255) under which two frames show the same shot
EVENT_TRANSITION = {"flash": "flash", "flash_black": "flash_black", "shake": "shake", "punch": "punch", "whip": "whip"}
MIN_GAP = 3             # frames between two events of a shot (Shot Assemble sub-cuts have at least 3)


@dataclass(frozen=True)
class Event:
    kind: str       # flash, flash_black, shake, punch, whip, push
    frame: int      # first frame
    frames: int     # length
    strength: float


def read_gray(path: Path, fps: Fraction, limit: int | None = None) -> np.ndarray:
    """Every frame of the video as a small gray image (N, 90, 160)."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-an", "-vf", f"scale={SIZE[0]}:{SIZE[1]}:flags=area,format=gray", "-f", "rawvideo", "-pix_fmt", "gray"]
    if limit:
        cmd += ["-frames:v", str(limit)]
    out = subprocess.run([*cmd, "-"], capture_output=True)
    if out.returncode:
        raise MajoorError(f"ffmpeg could not read the frames of the video: {out.stderr.decode(errors='replace')[:300]}")
    data = np.frombuffer(out.stdout, dtype=np.uint8)
    size = SIZE[0] * SIZE[1]
    return data[: len(data) // size * size].reshape(-1, SIZE[1], SIZE[0])


def global_motion(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """The translation (dx, dy, in pixels of 160) and the scale change between two gray frames, from a coarse optical flow fitted by least squares."""
    flow = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 2, 15, 2, 5, 1.1, 0)
    ys, xs = np.mgrid[4:SIZE[1] - 4:6, 4:SIZE[0] - 4:6]
    u = flow[4:SIZE[1] - 4:6, 4:SIZE[0] - 4:6, 0].ravel()
    v = flow[4:SIZE[1] - 4:6, 4:SIZE[0] - 4:6, 1].ravel()
    x = xs.ravel() - SIZE[0] / 2
    y = ys.ravel() - SIZE[1] / 2
    design = np.concatenate([np.stack([np.ones_like(x), np.zeros_like(x), x], 1), np.stack([np.zeros_like(x), np.ones_like(x), y], 1)])
    (dx, dy, s), *_ = np.linalg.lstsq(design, np.concatenate([u, v]), rcond=None)
    return float(dx), float(dy), float(s)


def measure(frames: np.ndarray) -> dict[str, np.ndarray]:
    """Per frame: the mean luma, and the motion from the previous frame (the first frame has none)."""
    luma = frames.reshape(len(frames), -1).mean(1)
    motion = np.zeros((len(frames), 3))
    for i in range(1, len(frames)):
        motion[i] = global_motion(frames[i - 1], frames[i])
    return {"luma": luma, "dx": motion[:, 0], "dy": motion[:, 1], "scale": motion[:, 2]}


def _baseline(luma: np.ndarray, i: int, width: int) -> float:
    near = np.r_[luma[max(0, i - width - 4):max(0, i - 1)], luma[i + width + 2:i + width + 6]]
    return float(np.median(near)) if len(near) else float(luma[i])


def detect_events(metrics: dict[str, np.ndarray]) -> list[Event]:
    """The events of the video, in frame order. A flash is a short rise (or fall) of the luma that comes back; a shake changes the direction of the motion every frame;
    a punch is a quick jump of the scale; a whip a big step of the picture; a push a steady growth of the scale."""
    luma, dx, dy, scale = metrics["luma"], metrics["dx"], metrics["dy"], metrics["scale"]
    n = len(luma)
    events: list[Event] = []
    taken = np.zeros(n, bool)

    i = 1
    while i < n:
        for width in range(1, FLASH_MAX + 1):
            base = _baseline(luma, i, width)
            rise = float(np.min(luma[i:i + width])) - base if i + width <= n else 0.0
            fall = base - float(np.max(luma[i:i + width])) if i + width <= n else 0.0
            after = abs(float(luma[min(i + width, n - 1)]) - base)
            if max(rise, fall) >= FLASH_RISE and after <= FLASH_BACK:
                kind = "flash" if rise >= fall else "flash_black"
                events.append(Event(kind, i, width, max(rise, fall)))
                taken[max(0, i - 1):i + width + 1] = True
                i += width
                break
        i += 1

    step = np.hypot(dx, dy)
    for i in range(1, n):
        if taken[i]:
            continue
        if step[i] >= WHIP_STEP:
            events.append(Event("whip", i, 1, float(step[i])))
            taken[i - 1:i + 2] = True
        elif abs(scale[i]) >= PUNCH_STEP:
            events.append(Event("punch", i, 1, float(scale[i])))
            taken[i - 1:i + 2] = True

    i = 1
    while i < n - SHAKE_MIN:
        j = i
        while j + 1 < n and not taken[j + 1] and step[j + 1] >= SHAKE_STEP and (dx[j] * dx[j + 1] < 0 or dy[j] * dy[j + 1] < 0):
            j += 1
        if j - i + 1 >= SHAKE_MIN:
            events.append(Event("shake", i, j - i + 1, float(np.mean(step[i:j + 1]))))
            taken[i:j + 1] = True
            i = j + 1
        else:
            i += 1

    i = 1
    while i < n:
        j = i
        while j + 1 < n and not taken[j + 1] and abs(scale[j + 1]) >= PUSH_STEP and np.sign(scale[j + 1]) == np.sign(scale[i]) and abs(scale[j + 1]) < PUNCH_STEP:
            j += 1
        if j - i + 1 >= PUSH_MIN:
            events.append(Event("push", i, j - i + 1, float(np.sum(scale[i:j + 1]))))
            taken[i:j + 1] = True
            i = j + 1
        else:
            i += 1
    return sorted(events, key=lambda e: e.frame)


def clean_cuts(cuts: list[int], events: list[Event], frames: np.ndarray, warnings: list[str]) -> list[int]:
    """A flash is not a cut: the cuts that a detector puts on the frames of a flash are dropped when the picture is the same before and after it.
    A cut inside a flash whose two sides differ stays, once, at the end of the flash."""
    kept = set(cuts)
    for e in events:
        if e.kind not in ("flash", "flash_black"):
            continue
        window = sorted(c for c in cuts if e.frame - 1 <= c <= e.frame + e.frames + 1)
        if not window:
            continue
        before, after = max(0, e.frame - 2), min(len(frames) - 1, e.frame + e.frames + 1)
        same = float(np.abs(frames[before].astype(np.int16) - frames[after].astype(np.int16)).mean()) <= SAME_SHOT
        drop = window if same else window[:-1]
        for c in drop:
            kept.discard(c)
            warnings.append(f"Cut at frame {c} removed: it sits on a {e.kind.replace('_', ' ')} of the picture")
    return sorted(kept)


def shot_fx(events: list[Event], start: int, end: int, camera: bool) -> dict:
    """What a shot [start, end) did, as a row of a plan: a transition into the shot, sub-cuts with a transition at each event inside it, and with camera a push over the shot.
    The events come with their frame in the video."""
    here = [e for e in events if start <= e.frame < end and e.kind != "push"]
    row: dict = {}
    opening = next((e for e in here if e.frame - start <= 1), None)
    if opening:
        row["transition"] = {"type": EVENT_TRANSITION[opening.kind], "frames": max(2, min(opening.frames + 2, 8))}
        here = [e for e in here if e is not opening]
    marks: list[Event] = []
    for e in here:
        if e.frame - start >= MIN_GAP and end - e.frame >= MIN_GAP and (not marks or e.frame - marks[-1].frame >= MIN_GAP):
            marks.append(e)
    if marks:
        bounds = [start, *[e.frame for e in marks], end]
        row["sub_cuts"] = [{"duration_frames": b - a, **({"transition": {"type": EVENT_TRANSITION[marks[k - 1].kind], "frames": max(2, min(marks[k - 1].frames + 2, 8))}} if k else {})}
                           for k, (a, b) in enumerate(zip(bounds, bounds[1:]))][:24]
    if camera:
        pushes = [e for e in events if e.kind == "push" and start <= e.frame < end]
        total = sum(e.strength for e in pushes)
        if abs(total) >= 0.04 and "sub_cuts" not in row:
            row["zoom"] = [1.0, round(min(1.0 + total, 1.4), 3)] if total > 0 else [round(min(1.0 - total, 1.4), 3), 1.0]
    return row
