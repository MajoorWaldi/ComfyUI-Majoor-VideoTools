"""A quick look at a generated take: is it black, white or only noise? Eight frames, OpenCV only.

Dark and static shots are normal in an edit (a silhouette, a macro of a frame), and so are busy ones (a neon arcade reads 1.7 on the noise ratio below, a sharp picture of
a face 0.4), so only the clear failures are caught: a take that is black or white from start to end, and one made of noise (the variance of the Laplacian over the variance
of the picture is 20 for white noise). A take whose face is smeared or whose body melts is NOT caught: no number of this kind told one from a good busy shot on the takes tried;
the judge of the Remix (an LLM that looks at the frames) is the tool for that."""
from pathlib import Path

import cv2
import numpy as np

SAMPLES = 8
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


def check_take(path: Path) -> tuple[bool, str]:
    """(ok, what is wrong, or the numbers that were read when nothing is)."""
    m = take_metrics(path)
    if not m["frames"]:
        return False, "no frame could be read"
    if m["luma_max"] < BLACK:
        return False, f"black from start to end (brightest frame {m['luma_max']:.1f} of 255)"
    if m["luma_min"] > WHITE:
        return False, f"white from start to end (darkest frame {m['luma_min']:.1f} of 255)"
    if m["noise_median"] > NOISY_MEDIAN:
        return False, f"only noise: ratio {m['noise_median']:.1f} (median over the frames), the limit is {NOISY_MEDIAN:g}"
    return True, f"fine: luma {m['luma_mean']:.0f}, noise {m['noise_mean']:.2f}"
