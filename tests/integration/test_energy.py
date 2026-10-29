import subprocess
from fractions import Fraction

import cv2
import numpy as np
import pytest

from majoor_videotools.core import energy
from majoor_videotools.core.fx import describe_shot
from majoor_videotools.core.scene_detection import detect_scenes


def _frame(base, f):
    s, tx, ty, add = 1.0, 0.0, 0.0, 0
    if f >= 90:
        s = 1.15
    if f >= 110:
        s = 1.15 * (1 + 0.006 * min(f - 110, 40))
    if 60 <= f < 70:
        tx, ty = 6 * (1 if f % 2 else -1), 4 * (-1 if f % 2 else 1)
    if 40 <= f < 42:
        add = 140
    M = np.float32([[s, 0, 320 - 320 * s + tx], [0, s, 180 - 180 * s + ty]])
    img = cv2.warpAffine(base, M, (640, 360), borderMode=cv2.BORDER_REFLECT)
    return np.clip(img.astype(np.int16) + add, 0, 255).astype(np.uint8)


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    """160 frames of one texture: a flash at 40-41, a shake at 60-69, a punch-in at 90, a slow push from 110."""
    rng = np.random.default_rng(3)
    base = cv2.normalize(cv2.GaussianBlur(rng.integers(0, 255, (360, 640), dtype=np.uint8), (0, 0), 6), None, 40, 200, cv2.NORM_MINMAX)
    path = tmp_path_factory.mktemp("energy") / "energy.mp4"
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "640x360", "-r", "24", "-i", "-", "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv420p", str(path)], stdin=subprocess.PIPE)
    for f in range(160):
        proc.stdin.write(_frame(base, f).tobytes())
    proc.stdin.close()
    proc.wait()
    return path


def test_the_events_of_a_video_are_found(video):
    events = energy.detect_events(energy.measure(energy.read_gray(video, Fraction(24))))
    kinds = {e.kind: e for e in events}
    assert abs(kinds["flash"].frame - 40) <= 1
    assert kinds["shake"].frame <= 62 and kinds["shake"].frame + kinds["shake"].frames >= 68
    assert abs(kinds["punch"].frame - 90) <= 1
    assert abs(kinds["push"].frame - 111) <= 3


def test_a_flash_is_not_a_cut_and_the_shot_gets_its_effects(video):
    shots = detect_scenes(video, video.parent / "projects", "manual", 0.5, 1, "", False, True, "events_and_camera").shots
    assert len(shots) == 1
    fx = shots[0].plan["fx"]
    assert [(c["frames"], c.get("transition", {}).get("type")) for c in fx["sub_cuts"]] == [(40, None), (20, "flash"), (30, "shake"), (70, "punch")]
    off = detect_scenes(video, video.parent / "projects", "manual", 0.5, 1, "", False, True, "off").shots
    assert off[0].plan is None

    shot = shots[0]  # what Select Shot does with the plan of a shot
    info, text = describe_shot(shot.shot_id, 0.0, float(shot.target_duration_seconds), shot.frame_count, shot.plan, 24.0)
    assert info["cut_count"] == 4 and "transition flash" in text
