"""Transitions that carry the motion of the takes, texts held long enough to be read, the colors of the film, time effects and looks,
their sounds, and titles that pass behind or come out from behind the subject."""
import json
import subprocess
from fractions import Fraction

import numpy as np
import pytest

from majoor_videotools.core import motion_sync
from majoor_videotools.core.fx import TECHNIQUES, TIME_EFFECTS, _common, segment_chain
from majoor_videotools.core.motion import behind_at, parse_layers
from majoor_videotools.core.motion_library import expand_rows
from majoor_videotools.core.motion_scenes import competing, readability
from majoor_videotools.core.motion_timing import shot_layers
from majoor_videotools.core.palette import palette
from majoor_videotools.core.sfx import CUES, TIME_CUES

FPS = Fraction(24)


def _clip(tmp_path, name="clip.mp4", source="testsrc2"):
    path = tmp_path / name
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{source}=size=320x180:rate=24:duration=2", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def _frames(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", "scale=32:18,format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 18, 32).astype(int)


def _render(tmp_path, source, spec, transition=None, frames=24):
    out = tmp_path / "out.mp4"
    chain = segment_chain(spec, frames, FPS, 320, 180, transition)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-vf", f"scale=320:180,{chain}", str(out)], check=True)
    return _frames(out)


def test_a_whip_says_which_way_the_picture_travels_and_a_still_take_keeps_a_plain_one():
    whip = _common({"transition": {"type": "whip", "direction": "up"}}, "t", FPS)["transition"]
    assert whip == {"type": "whip_v", "frames": 4, "direction": "up"}
    assert _common({"transition": "whip_left"}, "t", FPS)["transition"]["direction"] == "left"
    assert motion_sync.whip_direction(2.0, .3) == "right" and motion_sync.whip_direction(-.2, -1.5) == "up"
    assert motion_sync.whip_direction(.2, .1) is None


def test_the_drift_of_a_moving_take_gives_its_whip_a_way(tmp_path):
    rng = np.random.default_rng(2)
    texture = rng.integers(30, 220, (90, 320), dtype=np.uint8)
    path = tmp_path / "pan.mp4"
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "160x90", "-r", "24", "-i", "-",
                             "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv420p", str(path)], stdin=subprocess.PIPE)
    for i in range(12):  # the picture travels right, 3 pixels a frame
        proc.stdin.write(np.ascontiguousarray(texture[:, 80 - 3 * i:240 - 3 * i]).tobytes())
    proc.stdin.close()
    proc.wait()
    assert motion_sync.whip_direction(*motion_sync.take_drift(path)) == "right"


def test_a_directed_whip_slides_the_picture_in(tmp_path):
    source = _clip(tmp_path)
    still = _render(tmp_path, source, {})
    slid = _render(tmp_path, source, {}, {"type": "whip", "frames": 6, "direction": "left"})
    assert np.abs(slid[0] - still[0]).mean() > np.abs(slid[10] - still[10]).mean() + 5  # moved at first, settled after the transition


def test_a_text_too_short_to_read_is_lengthened_in_its_shot_or_becomes_a_texture():
    timeline = json.dumps([{"id": "SHOT_001", "start": 0, "duration": 4}, {"id": "SHOT_002", "start": 4, "duration": .4}])
    rows = [{"type": "text", "content": "THE NIGHT BELONGS TO US", "shot_id": "SHOT_001", "start": 1, "end": 1.3, "animation": "fade"},
            {"type": "text", "content": "GO", "shot_id": "SHOT_002", "start": 0, "end": .2, "animation": "fade", "out": "fade"}]
    message, texture = shot_layers(json.dumps(rows), timeline, 4.4, 24)[0]
    assert message["reading"] == "lengthened" and message["end"] - message["start"] >= 1.5 and message["end"] <= 4
    assert texture["reading"] == "texture" and texture["animation"] == "fade" and texture["out"] == "none" and texture["end"] == pytest.approx(4.4)
    layers = parse_layers(json.dumps([message, texture]), 4.4)
    assert not [w for w in readability(layers, 720, 1280, 4.4)["warnings"] if w["kind"] == "short_reading_window"]


def test_two_layers_fighting_for_one_moment_are_reported():
    layers = parse_layers(json.dumps([{"type": "effect", "kind": "glitch", "start": 0, "end": 1}, {"type": "effect", "kind": "glitch", "start": .5, "end": 1.5},
                                      {"type": "text", "content": "A", "position": "top", "start": 0, "end": 2}, {"type": "text", "content": "B", "position": "top", "start": 1, "end": 2},
                                      {"type": "text", "content": "C", "position": "bottom", "start": 1, "end": 2}]), 3)
    assert [(w["layer"], w["with"], w["kind"]) for w in competing(layers, 3)] == [(1, 0, "competing_effects"), (3, 2, "competing_texts")]


def test_the_palette_of_a_picture_gives_a_vivid_accent_even_when_it_covers_little():
    picture = np.full((60, 60, 3), (40, 38, 36), np.uint8)
    picture[:20] = (225, 222, 218)
    picture[50:, 50:] = (20, 120, 230)  # a small blue neon
    found = palette(picture.reshape(-1, 3))
    accent = tuple(int(found["accent"][i:i + 2], 16) for i in (1, 3, 5))
    assert accent[2] > accent[0] + 80  # blue, though the neon covers 3 % of the picture
    assert found["light"] == "#e1deda" and found["dark"] == "#282624"  # the light and the dark of the picture itself
    assert palette(np.full((40, 3), 128, np.uint8))["accent"] is None  # a grey picture has no accent


def test_time_effects_change_the_cut_and_keep_its_length(tmp_path):
    source = _clip(tmp_path)
    plain = _render(tmp_path, source, {})
    frozen = _render(tmp_path, source, {"time": "freeze"})
    assert len(frozen) == len(plain) == 24
    assert np.abs(frozen[-1] - frozen[14]).mean() * 3 < np.abs(plain[-1] - plain[14]).mean()  # it stops and holds (up to the noise of the encoder)
    stutter = _render(tmp_path, source, {"time": "stutter"})
    assert len(stutter) == 24 and np.abs(stutter[3] - plain[0]).mean() < np.abs(stutter[3] - plain[3]).mean()  # the first frames come again
    assert len(_render(tmp_path, source, {"time": "echo"})) == 24
    assert _common({"time": "trails"}, "t", FPS) == {"time": "echo"} and set(TIME_EFFECTS) == set(TIME_CUES)


@pytest.mark.parametrize("look", ["grain", "riso", "duotone", "vhs"])
def test_every_new_look_renders(tmp_path, look):
    assert len(_render(tmp_path, _clip(tmp_path), {"look": look})) == 24


@pytest.mark.parametrize("kind", ["iris", "blinds"])
def test_iris_and_blinds_open_the_picture_from_black(tmp_path, kind):
    frames = _render(tmp_path, _clip(tmp_path), {}, _common({"transition": kind}, "t", FPS)["transition"])
    assert frames[0].mean() < frames[12].mean() - 20 and kind in CUES


def test_every_effect_of_the_catalogue_exists():
    from majoor_videotools.core.fx import LOOKS, TRANSITIONS
    for level in TECHNIQUES.values():
        assert set(level["transitions"]) <= set(TRANSITIONS) and set(level["looks"]) <= set(LOOKS) and set(level["time"]) <= set(TIME_EFFECTS)


def test_a_title_can_pass_behind_the_subject_or_come_out_from_behind_it():
    through, emerge = expand_rows([{"template": "title_through", "start": 0, "end": 2, "title": "night"},
                                   {"template": "title_emerge", "start": 0, "end": 2, "title": "night"}])
    layers = parse_layers(json.dumps([through, emerge, {"type": "text", "content": "x", "behind": "sideways"}]), 3)
    assert [l["behind"] for l in layers] == ["through", "emerge", True] and all(l["needs_mask"] for l in layers)
    assert not behind_at(layers[0], .5, 3) and behind_at(layers[0], 1.5, 3)
    assert behind_at(layers[1], .5, 3) and not behind_at(layers[1], 1.5, 3)


def test_the_words_of_a_lyric_last_as_long_as_they_are_sung_and_never_pile_up():
    words = [{"word": w, "start": s} for w, s in (("veins", 0.0), ("Dracula", 0.42), ("steps", 0.88), ("out", 1.38), ("got", 1.79))]
    rows = expand_rows([{"template": "kinetic_lyrics", "start": 0, "end": 4, "words": words}])
    layers = shot_layers(json.dumps(rows), "[]", 4, 24)[0]
    assert [round(l["end"] - l["start"], 2) for l in layers[:4]] == [0.42, 0.46, 0.5, 0.42]  # until the next word, not to a reading time
    assert all(layers[i]["end"] <= layers[i + 1]["start"] + 1 / 24 for i in range(len(layers) - 1))  # one word at a time
    assert all(l["reading"] == "exact" for l in layers)
    assert not [w for w in readability(parse_layers(json.dumps(layers), 4), 720, 1280, 4)["warnings"] if w["kind"] == "short_reading_window"]
