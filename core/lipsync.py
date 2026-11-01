"""Measured lip sync: does the mouth of a generated take move when the voice sounds?

No model and no network. Two signals are read at the frame rate of the take and compared:
the *speech* (loudness of the take's own sound, or of the sound it was made for) and the *mouth*
(how much the pixels of the mouth region change from one frame to the next). A mouth that follows
the voice makes the two curves rise and fall together, possibly a few frames apart; the report gives
that agreement (`score`), the delay (`lag_ms`) and a verdict. It measures movement, not phonemes:
a take with a mouth that moves in time with the voice passes, a take with a still or unrelated mouth fails.
The "voice" is the loudness of the sound: music or noise under the voice, or a camera that moves, make the result less reliable.

The verdict is `pass`, `fail`, or `unmeasured` (no face found, no speech, or too short): an unmeasured
take is never turned into a pass or a failure."""
import math
import subprocess
from pathlib import Path

import numpy as np

from .errors import MajoorError

MIN_SECONDS = 1.0       # shorter than this carries too little to correlate
MAX_LAG_SECONDS = .25   # a mouth is never taken to lead or trail the voice by more than this
PASS_SCORE = .45        # correlation of the two curves at their best delay
MIN_SPEECH_RATIO = .15  # share of frames where the voice is audible; less is a take with no one speaking
MIN_FACE_RATIO = .5     # share of frames in which the mouth region could be located


def speech_envelope(samples, rate: int, fps: float, frames: int) -> np.ndarray:
    """Loudness (RMS) of the sound at each video frame, 0..1 against the loudest frame. Zeros when the track is silent."""
    samples = np.asarray(samples, dtype=np.float64)
    if rate <= 0 or fps <= 0 or frames <= 0:
        raise MajoorError("Lip sync needs a positive sample rate, frame rate and frame count")
    if samples.ndim != 1 or not np.isfinite(samples).all():
        raise MajoorError("Lip sync needs finite mono audio")
    edges = np.round(np.arange(frames + 1) / fps * rate).astype(int).clip(0, len(samples))
    levels = np.array([math.sqrt(float(np.mean(samples[a:b] ** 2))) if b > a else 0.0 for a, b in zip(edges, edges[1:])])
    peak = levels.max() if len(levels) else 0.0
    return levels / peak if peak > 1e-6 else np.zeros(frames)


def mouth_motion(crops) -> np.ndarray:
    """Movement of the mouth region at each frame: the mean absolute change from the previous frame.

    `crops` are equally sized gray images (uint8 or float) of that region. A frame without a face is None, and so is not measured (NaN);
    the same goes for a frame that has no earlier frame to compare with (the first, or the one after a gap)."""
    motion, previous = [], None
    for crop in crops:
        if crop is None:
            motion.append(math.nan)
            previous = None
            continue
        current = np.asarray(crop, dtype=np.float64)
        motion.append(math.nan if previous is None else float(np.mean(np.abs(current - previous))))
        previous = current
    return np.array(motion)


def lagged_correlation(mouth, speech, max_lag: int) -> tuple[float, int]:
    """(best correlation, lag in frames) of the mouth curve against the speech curve, trying every shift up to `max_lag` each way.

    A positive lag means the mouth follows the voice. NaN frames (no face) are left out of each comparison."""
    mouth, speech = np.asarray(mouth, dtype=np.float64), np.asarray(speech, dtype=np.float64)
    best, best_lag = -1.0, 0
    for lag in range(-max_lag, max_lag + 1):
        a, b = (mouth[lag:], speech[:len(speech) - lag]) if lag >= 0 else (mouth[:lag], speech[-lag:])
        n = min(len(a), len(b))
        a, b = a[:n], b[:n]
        keep = np.isfinite(a) & np.isfinite(b)
        if keep.sum() < 6:
            continue
        a, b = a[keep], b[keep]
        if a.std() < 1e-9 or b.std() < 1e-9:
            continue
        score = float(np.corrcoef(a, b)[0, 1])
        if score > best:
            best, best_lag = score, lag
    return best, best_lag


def lipsync_report(mouth, speech, fps: float) -> dict:
    """The verdict on one take from its mouth-motion and speech curves (one value per frame, same length)."""
    mouth, speech = np.asarray(mouth, dtype=np.float64), np.asarray(speech, dtype=np.float64)
    frames = min(len(mouth), len(speech))
    mouth, speech = mouth[:frames], speech[:frames]
    report = {"status": "unmeasured", "reason": "", "score": None, "lag_ms": None, "frames": int(frames),
              "face_ratio": 0.0, "speech_ratio": 0.0}
    if fps <= 0 or frames < MIN_SECONDS * fps:
        report["reason"] = "the take is too short to measure"
        return report
    report["face_ratio"] = round(float(np.isfinite(mouth).mean()), 3)
    report["speech_ratio"] = round(float((speech > .2).mean()), 3)
    if report["face_ratio"] < MIN_FACE_RATIO:
        report["reason"] = "no face found in most of the take"
        return report
    if report["speech_ratio"] < MIN_SPEECH_RATIO:
        report["reason"] = "no one speaks in this take"
        return report
    seen = np.isfinite(mouth)
    if mouth[seen].std() < 1e-9:
        report.update(status="fail", reason="the mouth does not move", score=0.0, lag_ms=0)
        return report
    if speech.std() < 1e-9:
        report["reason"] = "the voice has no variation to follow"
        return report
    score, lag = lagged_correlation(mouth, speech, max(1, round(MAX_LAG_SECONDS * fps)))
    if score <= -1:
        report["reason"] = "too few frames with both a face and a voice"
        return report
    report.update(score=round(score, 3), lag_ms=round(lag / fps * 1000))
    report["status"] = "pass" if score >= PASS_SCORE else "fail"
    report["reason"] = ("the mouth follows the voice" if report["status"] == "pass"
                        else "the mouth movement does not follow the voice")
    return report


def needs_retake(report: dict, attempt: int, max_attempts: int = 3) -> bool:
    """A failed take is made again until `max_attempts` takes were tried (`attempt` counts from 1). A take that could not be measured is kept."""
    return report.get("status") == "fail" and attempt < max_attempts


def next_seed(seed: int, attempt: int) -> int:
    """A different seed for each new attempt, the same one for the same (seed, attempt)."""
    return (int(seed) + 7919 * int(attempt)) % (2 ** 31)


def _unmeasured(reason: str, frames: int = 0) -> dict:
    return {"status": "unmeasured", "reason": reason, "score": None, "lag_ms": None, "frames": frames, "face_ratio": 0.0, "speech_ratio": 0.0}


def parse_region(text) -> tuple[float, float, float, float] | None:
    """A fixed mouth region "x,y,w,h" as fractions of the frame (0..1), for a take framed the same way throughout. Empty: find the face."""
    if text is None or not str(text).strip():
        return None
    try:
        x, y, w, h = (float(v) for v in str(text).split(","))
    except ValueError:
        raise MajoorError('The mouth region is four numbers "x,y,w,h" between 0 and 1') from None
    if not all(math.isfinite(v) for v in (x, y, w, h)) or min(x, y) < 0 or min(w, h) <= 0 or x + w > 1.0001 or y + h > 1.0001:
        raise MajoorError('The mouth region "x,y,w,h" must lie inside the frame (numbers between 0 and 1)')
    return x, y, w, h


def _face_finder(cv2):
    """A function gray image -> list of (x, y, w, h) faces, or None when this OpenCV has no face detector (OpenCV 5 dropped the Haar cascades)."""
    classifier = getattr(cv2, "CascadeClassifier", None)
    if classifier is None:
        return None
    detector = classifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if detector.empty():
        return None
    return lambda gray: detector.detectMultiScale(gray, 1.1, 5, minSize=(max(24, gray.shape[1] // 10),) * 2)


def measure_video(path, audio=None, *, region=None, binary: str = "ffmpeg") -> dict:
    """Read a take from disk and return its report. `audio` is a wav/mp4 to take the voice from; by default the take's own sound.

    The face is found with OpenCV's frontal-face detector on every frame and the box smoothed; the mouth region is the lower third of the
    face. With `region` (see `parse_region`) that part of the frame is used instead and no detector is needed. When no face can be found
    (or this OpenCV has no detector and no region was given) the report is `unmeasured`."""
    try:
        import cv2
    except ImportError:
        return _unmeasured("OpenCV is not installed")
    find = None if region else _face_finder(cv2)
    if region is None and find is None:
        return _unmeasured("this OpenCV has no face detector: give the mouth region")
    path = Path(path)
    capture = cv2.VideoCapture(str(path))
    try:
        fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
        if fps <= 0:
            raise MajoorError(f"Cannot read the frame rate of {path.name}")
        crops, box = [], None
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            crop = None
            if region:
                height, width = gray.shape
                crop = gray[int(region[1] * height):int((region[1] + region[3]) * height), int(region[0] * width):int((region[0] + region[2]) * width)]
            else:
                scale = min(1.0, 320 / gray.shape[1])  # the face is looked for on a small copy: fast, and enough
                small = cv2.resize(gray, None, fx=scale, fy=scale) if scale < 1 else gray
                found = find(small)
                if len(found):
                    new = np.array(max(found, key=lambda f: f[2] * f[3]), dtype=np.float64) / scale
                    box = new if box is None else .6 * box + .4 * new  # smoothed: a box that jumps would read as a moving mouth
                else:
                    box = None
                if box is not None:
                    x, y, w, h = (int(round(v)) for v in box)
                    crop = gray[max(0, y + 2 * h // 3):max(0, y + h), max(0, x + w // 5):max(0, x + 4 * w // 5)]
            crops.append(cv2.resize(crop, (48, 24)) if crop is not None and crop.size else None)
    finally:
        capture.release()
    if not crops:
        raise MajoorError(f"{path.name} has no readable frames")
    samples, rate = _read_audio(Path(audio) if audio else path, binary)
    if not len(samples):
        return _unmeasured("the take has no sound", len(crops))
    return lipsync_report(mouth_motion(crops), speech_envelope(samples, rate, fps, len(crops)), fps)


def _read_audio(path: Path, binary: str) -> tuple[np.ndarray, int]:
    rate = 16000
    command = [binary, "-v", "error", "-nostdin", "-i", str(path), "-vn", "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"]
    try:
        result = subprocess.run(command, capture_output=True, timeout=120, check=False)
    except subprocess.TimeoutExpired:
        raise MajoorError("ffmpeg took too long to read the sound of the take") from None
    except FileNotFoundError:
        raise MajoorError("ffmpeg was not found") from None
    if result.returncode:
        return np.zeros(0), rate  # no audio stream
    samples = np.frombuffer(result.stdout, dtype="<f4").astype(np.float64)
    return (samples if np.isfinite(samples).all() else np.zeros(0)), rate
