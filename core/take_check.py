"""A quick look at a generated take: is it black, white or only noise? Eight frames, OpenCV only.

Dark and static shots are normal in an edit (a silhouette, a macro of a frame), and so are busy ones (a neon arcade reads 1.7 on the noise ratio below, a sharp picture of
a face 0.4), so only the clear failures are caught: a take that is black or white from start to end, and one made of noise (the variance of the Laplacian over the variance
of the picture is 20 for white noise). A take whose face is smeared or whose body melts is NOT caught: no number of this kind told one from a good busy shot on the takes tried;
the judge of the Remix (an LLM that looks at the frames) is the tool for that."""
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

from ..adapters.ffmpeg import CREATIONFLAGS, find_binary

SAMPLES = 8
HEIGHTS = {"480p": 480, "720p": 720, "1080p": 1080}  # the short side of a take, as an API model names its resolutions
SIZE_TOLERANCE = 0.08  # a model rounds a size to a multiple of 16 or 32: 8 % is rounding, more is another resolution
SECONDS_TOLERANCE = 0.15  # a take may be a few frames off the length asked; this is the share of the length, and never less than 0.25 s


def probe_take(path: Path) -> dict:
    """What the file really is, read with ffprobe: width, height, seconds, frame rate. {} when ffprobe cannot read it (the check then says so)."""
    try:
        out = subprocess.run([find_binary("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate,duration:format=duration",
                              "-of", "json", str(path)], capture_output=True, creationflags=CREATIONFLAGS, timeout=60)
        data = json.loads(out.stdout or b"{}")
        stream = (data.get("streams") or [{}])[0]
        num, _, den = str(stream.get("r_frame_rate", "0/1")).partition("/")
        seconds = stream.get("duration") or (data.get("format") or {}).get("duration")
        return {"width": int(stream["width"]), "height": int(stream["height"]), "fps": float(num) / float(den or 1) if float(den or 1) else 0.0, "seconds": float(seconds) if seconds not in (None, "N/A") else 0.0}
    except Exception:
        return {}


def check_settings(path: Path, aspect: str = "", resolution: str = "", seconds: float = 0.0, task: str = "reference") -> tuple[bool, str]:
    """Is the take the one the call asked for: its shape (9:16, 16:9, 1:1...), its resolution (480p/720p/1080p, the short side) and its length?
    Nothing asked, nothing checked. A take off its settings is not used: it is made again (twelve clips of one film came back in the wrong shape, seven billed at 720p).
    A take that cannot be measured (no ffprobe, a file it cannot read) is not called wrong: a retry is paid, and it would be measured no better, so
    the check says so and goes on to the frames. An edit (task=edit) keeps the shape and the length of its source, so only its resolution is checked."""
    if task == "edit":
        aspect, seconds = "", 0.0
    if not (aspect or resolution or seconds):
        return True, "no settings to check"
    found = probe_take(path)
    if not found:
        return True, "the settings were not checked: ffprobe could not read the take"
    width, height = found["width"], found["height"]
    if aspect:
        try:
            w, h = (float(x) for x in aspect.split(":"))
        except ValueError:
            return False, f"the shape {aspect!r} is not a ratio such as 9:16"
        if abs(width / height - w / h) > 0.03 * (w / h):
            return False, f"the shape is {width}x{height} ({width / height:.2f}), {aspect} was asked ({w / h:.2f})"
    if resolution and resolution.lower() in HEIGHTS:
        short = min(width, height)
        if abs(short - HEIGHTS[resolution.lower()]) > SIZE_TOLERANCE * HEIGHTS[resolution.lower()]:
            return False, f"the short side is {short} px, {resolution} was asked ({HEIGHTS[resolution.lower()]} px)"
    if seconds > 0 and found["seconds"] > 0 and abs(found["seconds"] - seconds) > max(0.25, SECONDS_TOLERANCE * seconds):
        return False, f"the take lasts {found['seconds']:.2f} s, {seconds:g} s was asked"
    return True, f"{width}x{height}, {found['seconds']:.2f} s, {found['fps']:.0f} fps"
SIZE = 192
BLACK, WHITE = 2.0, 250.0  # mean luma of every frame
NOISY_MEDIAN = 6.0  # median over the frames of the variance of the Laplacian over the variance of the picture


def take_metrics(path: Path) -> dict:
    capture = cv2.VideoCapture(str(path))
    count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    rows = []
    for k in range(SAMPLES):
        capture.set(cv2.CAP_PROP_POS_FRAMES, int((k + 0.5) * count / SAMPLES))
        ok, frame = capture.read()
        if not ok:
            continue
        gray = cv2.cvtColor(cv2.resize(frame, (SIZE, max(SIZE * frame.shape[0] // frame.shape[1], 8))), cv2.COLOR_BGR2GRAY).astype(np.float32)
        rows.append((float(gray.mean()), float(cv2.Laplacian(gray, cv2.CV_32F).var() / (gray.var() + 1.0))))
    capture.release()
    if not rows:
        return {"frames": 0}
    luma, ratio = np.array(rows).T
    return {"frames": len(rows), "luma_min": float(luma.min()), "luma_max": float(luma.max()), "luma_mean": float(luma.mean()), "noise_median": float(np.median(ratio)), "noise_mean": float(ratio.mean())}


def check_take(path: Path, aspect: str = "", resolution: str = "", seconds: float = 0.0, task: str = "reference") -> tuple[bool, str]:
    """(ok, what is wrong, or the numbers that were read when nothing is). The measure of the file (ffprobe) comes first, then the look of eight frames."""
    asked, said = check_settings(path, aspect, resolution, seconds, task)
    if not asked:
        return False, said
    m = take_metrics(path)
    if not m["frames"]:
        return False, "no frame could be read"
    if m["luma_max"] < BLACK:
        return False, f"black from start to end (brightest frame {m['luma_max']:.1f} of 255)"
    if m["luma_min"] > WHITE:
        return False, f"white from start to end (darkest frame {m['luma_min']:.1f} of 255)"
    if m["noise_median"] > NOISY_MEDIAN:
        return False, f"only noise: ratio {m['noise_median']:.1f} (median over the frames), the limit is {NOISY_MEDIAN:g}"
    measured = f"{said}, " if (said != "no settings to check") else ""
    return True, f"fine: {measured}luma {m['luma_mean']:.0f}, noise {m['noise_mean']:.2f}"
