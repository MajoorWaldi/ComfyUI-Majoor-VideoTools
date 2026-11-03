"""The energy of an edit, measured: flashes, shakes, punch-ins, whips and camera moves of a video, frame by frame.

A generated take comes back calmer than the footage it replaces: the flashes, the shake bursts and the punch-ins of the original are lost. This module measures them on the
original (a small gray copy of every frame: the luma, and the global motion between two frames: a translation and a scale), cleans the cuts of what a flash
makes of them, and writes what a shot did as the effects of a plan row (a transition into the shot, sub-cuts with a transition at each event, a push-in), which
Shot Assemble applies to the generated take."""
import subprocess
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

from .errors import MajoorError
from ..adapters.ffmpeg import CREATIONFLAGS, find_binary

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
COVER_STEP = 20.0       # mean difference (of 255) between two frames that starts a covered transition (hands, a whip, a blur across the picture)
COVER_KEEP = 10.0       # ... and keeps it going
COVER_MIN = 3           # frames
COVER_CHANGE = 0.25     # colour distance (Bhattacharyya, hue and saturation) between the calm frames on the two sides: another shot behind the cover
COVER_PEAK = 0.22       # colour distance of the most covered frame from both sides: something crossed the picture, not a glitch on the same shot
COVER_VERSION = 2       # in the id of a project: a project detected under other covered-cut rules keeps its own cuts
COVER_SHOT = 8         # frames: a covered cut never leaves a shorter piece (the cover alone, at the start of the video or next to a hard cut)
COPY_NEAR = 30.0        # mean difference (of 255) under which a frame of a take repeats a frame of its reference video
COPY_JUMP = 15.0        # how much further from the reference the rest of the take must be: the copy ends on a cut to new content
EVENT_TRANSITION = {"flash": "flash", "flash_black": "flash_black", "shake": "shake", "punch": "punch", "whip": "whip"}
MIN_GAP = 3             # frames between two events of a shot (Shot Assemble sub-cuts have at least 3)


@dataclass(frozen=True)
class Event:
    kind: str       # flash, flash_black, shake, punch, whip, push
    frame: int      # first frame
    frames: int     # length
    strength: float


def summarize_energy(events, cut_frames, duration_seconds) -> dict:
    if duration_seconds <= 0:
        raise ValueError('Energy measurement needs a positive duration')
    return {'schema_version':1,'duration_seconds':float(duration_seconds),
            'cut_rate':len(set(cut_frames))/duration_seconds,
            **{name+'_rate':sum(e.kind==name for e in events)/duration_seconds for name in ('flash','shake','punch','whip','push')}}


def compare_energy(reference, result) -> dict:
    if reference is None or result is None:
        return {'status':'unmeasured','reference':reference,'result':result,'ratios':{}}
    return {'status':'measured','reference':reference,'result':result,
            'ratios':{k:result[k]/value if value else None for k,value in reference.items() if k.endswith('_rate') and k in result}}


def read_gray(path: Path, fps: Fraction, limit: int | None = None, color: bool = False, start: float = 0.0) -> np.ndarray:
    """Every frame of the video as a small gray image (N, 90, 160), or with `color` a small BGR image (N, 90, 160, 3). `start`: seconds skipped first."""
    fmt = "bgr24" if color else "gray"
    seek = ["-ss", f"{start:.6f}"] if start > 0 else []
    cmd = [find_binary('ffmpeg'), "-v", "error", *seek, "-i", str(path), "-an", "-vf", f"scale={SIZE[0]}:{SIZE[1]}:flags=area,format={fmt}", "-f", "rawvideo", "-pix_fmt", fmt]
    if limit:
        cmd += ["-frames:v", str(limit)]
    with tempfile.TemporaryFile() as stream:
        try:
            out=subprocess.run([*cmd,'-'],stdout=stream,stderr=subprocess.PIPE,creationflags=CREATIONFLAGS,timeout=600)
        except subprocess.TimeoutExpired:
            raise MajoorError('ffmpeg exceeded its 600 second limit while reading the frames') from None
        if out.returncode:
            raise MajoorError(f'ffmpeg could not read the frames: {out.stderr.decode(errors="replace")[:300]}')
        size=SIZE[0]*SIZE[1]*(3 if color else 1)
        count=stream.tell()//size
        if not count:
            raise MajoorError('The video contains no readable frames')
        return np.memmap(stream,dtype=np.uint8,mode='r',shape=(count,SIZE[1],SIZE[0],3) if color else (count,SIZE[1],SIZE[0]))


def _nearest(take: np.ndarray, source: np.ndarray) -> list[float]:
    """For each frame of a take, the mean difference (of 255) to the closest frame of its source."""
    return [min(float(np.abs(t.astype(np.int16) - s.astype(np.int16)).mean()) for s in source) for t in take]


def source_likeness(take: np.ndarray, source: np.ndarray) -> float:
    """How far a take stays from its source shot, over the frames given (the part the edit keeps): the mean of the difference of each frame to
    the closest source frame. Under COPY_NEAR the take mostly repeats the source (the person it was asked to replace); a take that replaced
    the person stays far above it, the hands or the blur of a transition it shares with the source being only a few frames."""
    return float(np.mean(_nearest(take, source))) if len(take) and len(source) else 255.0


def copying_takes(distances: list[float]) -> list[bool]:
    """Which takes of a shot repeat their source, from their source_likeness: under COPY_NEAR, or COPY_JUMP closer to the source than another take
    (a take that replaced the person is far from the source; how far depends on the shot, so two takes are compared with each other)."""
    return [d < COPY_NEAR or any(d < other - COPY_JUMP for other in distances) for d in distances]


def copied_lead(take: np.ndarray, source: np.ndarray, needed: int) -> int:
    """How many first frames of a generated take repeat its reference video before the take cuts to what was asked: a model given the source shot
    as a reference sometimes opens on a copy of it (the person it was asked to replace) for a fraction of a second. `take` and `source` are small
    gray frames (read_gray); `source` covers the shot and a little around it. 0 when the take does not open on a copy; never so many that fewer
    than `needed` frames are left (a part of the copy then stays)."""
    n = len(take)
    if n < 2 or not len(source):
        return 0
    near = _nearest(take, source)
    best, lead = COPY_JUMP, 0
    for c in range(1, min(n // 2, n - needed) + 1):
        before, after = float(np.mean(near[:c])), float(np.mean(near[c:]))
        if before <= COPY_NEAR and after - before >= best:
            best, lead = after - before, c
    return lead


def covered_cuts(frames: np.ndarray, cuts: list[int]) -> list[int]:
    """The cuts hidden behind something that crosses the whole picture (hands clapping over the lens, a whip, a blur): a cut detector misses them,
    the change being spread over several frames. A burst of motion between two calm frames is a cut when the colours of its two sides differ and its
    most covered frame differs from both; the cut goes on that frame, so each shot keeps its half of the transition. `frames` are small BGR frames
    (read_gray with color); the cuts already found are kept and a burst next to one of them adds nothing."""
    n = len(frames)
    def gray(k):  # one frame at a time: a long video is never held whole in memory
        return cv2.cvtColor(np.asarray(frames[k]), cv2.COLOR_BGR2GRAY).astype(np.int16)
    def far(a, b):
        return float(np.abs(gray(a) - gray(b)).mean())
    def colour(a, b):
        ha, hb = (cv2.calcHist([cv2.cvtColor(np.asarray(frames[k]), cv2.COLOR_BGR2HSV)], [0, 1], None, [16, 8], [0, 180, 0, 256]) for k in (a, b))
        return cv2.compareHist(cv2.normalize(ha, ha), cv2.normalize(hb, hb), cv2.HISTCMP_BHATTACHARYYA)
    step, previous = np.zeros(n), gray(0) if n else None
    for k in range(1, n):
        current = gray(k)
        step[k] = float(np.abs(current - previous).mean())
        previous = current
    found, i = [], 1
    while i < n:
        if step[i] < COVER_STEP:
            i += 1
            continue
        j = i
        while j + 1 < n and step[j + 1] >= COVER_KEEP:
            j += 1
        before, after = i - 1, j + 1
        if j - i + 1 >= COVER_MIN and after < n and not any(before - 1 <= c <= after + 1 for c in cuts):
            peak = max(range(i, j + 1), key=lambda k: min(far(k, before), far(k, after)))
            if colour(before, after) >= COVER_CHANGE and min(colour(peak, before), colour(peak, after)) >= COVER_PEAK:
                found.append(peak)
        i = j + 1
    kept, bounds = [], sorted({0, n, *cuts})
    for peak in found:  # a piece shorter than COVER_SHOT is only the cover: it stays at the edge of its neighbour
        previous = max([b for b in bounds if b < peak] + kept)
        following = min(b for b in bounds if b > peak)
        if peak - previous >= COVER_SHOT and following - peak >= COVER_SHOT:
            kept.append(peak)
    return sorted({*cuts, *kept})


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
