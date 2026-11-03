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


def _look(seed, hue):
    """A small BGR picture of one look: a texture in one hue."""
    rng = np.random.default_rng(seed)
    value = cv2.GaussianBlur(rng.integers(60, 230, (90, 160), dtype=np.uint8), (0, 0), 3)
    hsv = np.dstack([np.full((90, 160), hue, np.uint8), np.full((90, 160), 170, np.uint8), value])
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def _clap(first, second, calm=10, cover=8):
    """Calm frames of `first`, two hands closing over the lens and opening on `second`, calm frames of `second`."""
    hand = np.empty((90, 160, 3), np.uint8)
    hand[:] = (120, 150, 225)  # skin, in BGR
    frames = [first] * calm
    for k in range(cover):
        width = int(80 * (k + 1) / (cover // 2)) if k < cover // 2 else int(80 * (cover - k - 1) / (cover // 2))
        picture = (first if k < cover // 2 else second).copy()
        picture[:, :width], picture[:, 160 - width:] = hand[:, :width], hand[:, 160 - width:]
        frames.append(picture)
    return np.stack(frames + [second] * calm)


def test_a_cut_hidden_behind_hands_over_the_lens_is_found_on_its_most_covered_frame():
    frames = _clap(_look(1, 10), _look(2, 110))
    cuts = energy.covered_cuts(frames, [])
    assert len(cuts) == 1 and 12 <= cuts[0] <= 15  # the hands cover the whole picture at frames 13 and 14
    assert energy.covered_cuts(frames, [14]) == [14]  # a cut the detector found already is not doubled


def test_a_cover_next_to_the_start_or_a_hard_cut_stays_on_the_edge_of_its_neighbour():
    frames = _clap(_look(1, 10), _look(2, 110), calm=2)  # the video starts two frames before the hands
    assert energy.covered_cuts(frames, []) == []
    frames = _clap(_look(1, 10), _look(2, 110))
    assert energy.covered_cuts(frames, [10]) == [10]  # a hard cut just before the hands: the hands stay at the start of the next shot


def test_a_take_that_opens_on_a_copy_of_its_source_starts_after_the_copy():
    gray = lambda look: cv2.cvtColor(look, cv2.COLOR_BGR2GRAY)
    source = np.stack([gray(_look(1, 10))] * 12)
    new = gray(_look(5, 60)) // 2 + 100  # what was asked: other content, far from the source
    copied = np.stack([source[0]] * 5 + [new] * 17)
    assert energy.copied_lead(copied, source, 12) == 5
    assert energy.copied_lead(np.stack([new] * 22), source, 12) == 0  # a clean take keeps its start
    assert energy.copied_lead(copied, source, 20) == 2  # the shot needs 20 of the 22 frames: only 2 of the copy go


def test_a_take_that_repeats_its_source_stays_close_to_it():
    gray = lambda look: cv2.cvtColor(look, cv2.COLOR_BGR2GRAY)
    source = np.stack([gray(_look(1, 10))] * 12)
    replaced = np.stack([gray(_look(5, 60)) // 2 + 100] * 13)
    assert energy.source_likeness(source[:5], source) == 0.0
    assert energy.source_likeness(replaced, source) > energy.COPY_NEAR > energy.source_likeness(np.concatenate([source[:10], replaced[:3]]), source)


def test_hands_over_the_lens_on_the_same_look_are_not_a_cut():
    look = _look(1, 10)
    assert energy.covered_cuts(_clap(look, look), []) == []
    calm = np.stack([look] * 30)
    assert energy.covered_cuts(calm, []) == []


def test_covered_transitions_give_a_new_project_only_when_they_are_used():
    from majoor_videotools.core.scene_detection import project_id_for
    assert project_id_for("f", "adaptive", .5, 2, "", "events", False) == project_id_for("f", "adaptive", .5, 2, "", "events")  # earlier projects keep their id
    assert project_id_for("f", "adaptive", .5, 2, "", "events", True) != project_id_for("f", "adaptive", .5, 2, "", "events")
    assert project_id_for("f", "manual", .5, 2, "12", "off", True) == project_id_for("f", "manual", .5, 2, "12")  # manual cuts are the cuts given


def test_of_two_takes_the_one_much_closer_to_the_source_repeats_it():
    assert energy.copying_takes([48.7, 19.5]) == [False, True]
    assert energy.copying_takes([63.3, 34.2]) == [False, True]  # above COPY_NEAR, but 29 closer to the source than the other take
    assert energy.copying_takes([48.0, 41.0]) == [False, False]  # two takes that both replaced the person
    assert energy.copying_takes([22.0]) == [True]
