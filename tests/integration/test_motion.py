import json
import subprocess

import numpy as np
import pytest

from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.media_probe import probe
from majoor_videotools.core.motion import parse_layers, render_motion


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    """4 s of a mid-gray picture at 24 fps with a 440 Hz tone."""
    from majoor_videotools.core.hyperframes import runtime_paths
    try:
        runtime_paths()
    except RuntimeError:
        pytest.skip('Optional local HyperFrames runtime is required for compositor integration tests')
    path = tmp_path_factory.mktemp("motion") / "gray.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x808080:s=320x240:r=24:d=4", "-f", "lavfi", "-i", "sine=f=440:d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path


def _frame(path, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(240, 320, 3).astype(int)


def test_the_layers_are_checked_and_completed():
    layers = parse_layers('```json\n{"layers": [{"type": "text", "content": "hello", "size": 0.9, "start": "50%", "animation": "spin"}, {"type": "brackets", "rect": [0.1, 0.1, 0.3, 0.3]}]}\n```', 4.0)
    assert layers[0]["start"] == 2.0 and layers[0]["size"] == 0.6 and layers[0]["animation"] == "none" and layers[0]["end"] is None  # out of range and unknown names are brought back, not refused
    assert layers[1]["type"] == "brackets" and layers[1]["rect"] == [0.1, 0.1, 0.3, 0.3]
    for bad, message in (("nope", "not valid JSON"), ('{"layers": 3}', "must be a list")):
        with pytest.raises(MajoorError, match=message):
            parse_layers(bad, 4.0)
    skipped = []  # a layer that cannot be read is left out and said, the others stay
    kept = parse_layers('[{"type": "star"}, {"type": "text"}, {"type": "box", "rect": [1, 2]}, {"type": "text", "content": "ok", "repeat": "x"}]', 4.0, skipped)
    assert [layer["type"] for layer in kept] == ["box"] and kept[0]["rect"] == [0.25, 0.25, 0.5, 0.5]
    assert len(skipped) == 3 and "unknown type" in skipped[0]


def test_a_text_appears_letter_by_letter_in_its_time_and_the_audio_stays(video, tmp_path):
    layers = parse_layers(json.dumps([{"type": "text", "content": "WHICH ONE", "position": "center", "size": 0.3, "color": "#ff0000", "start": 1.0, "end": 3.0, "animation": "typewriter", "in_time": 1.0},
                                      {"type": "brackets", "rect": [0.05, 0.05, 0.3, 0.3], "color": "#00ff00", "start": 0.5, "animation": "draw"}]), 4.0)
    out = tmp_path / "out.mp4"
    steps = []
    render_motion(video, layers, out, on_progress=steps.append)
    before, early, late, after = (_frame(out, t) for t in (0.2, 1.2, 2.2, 3.5))
    assert before.min() > 100 and before.max() < 160  # nothing yet: the gray picture only
    red = lambda f: int(((f[..., 0] > 200) & (f[..., 1] < 60)).sum())  # noqa: E731
    assert 0 < red(early) < red(late) and red(after) == 0  # more letters later, gone after the end
    assert int(((_frame(out, 2.2)[..., 1] > 200) & (_frame(out, 2.2)[..., 0] < 60)).sum()) > 0  # the brackets are drawn
    info = probe(out, with_packets=False)
    assert info.has_audio and info.frame_count == 96 and info.display_size == (320, 240)
    assert steps and steps[-1] <= 1.0


def test_every_animation_renders_without_error(video, tmp_path):
    rows = [{"type": "text", "content": "A", "animation": a, "start": 0.2, "end": 0.9, "out": "fade", "background": "black", "stroke": 0.05} for a in ("none", "fade", "pop", "slide_up", "slide_down", "slide_left", "slide_right", "typewriter", "glitch", "shake")]
    rows.append({"type": "box", "rect": [0, 0.8, 1, 0.2], "color": "black", "opacity": 0.5, "animation": "slide_up"})
    render_motion(video, parse_layers(json.dumps(rows), 4.0), tmp_path / "all.mp4")
    assert probe(tmp_path / "all.mp4", with_packets=False).frame_count == 96


def _masks(frames=96):
    mask = np.zeros((frames, 240, 320), np.float32)
    mask[:, 60:180, 110:210] = 1
    return mask


def test_outline_effects_and_tracking_need_the_mask_and_draw_around_the_subject(video, tmp_path):
    layers = parse_layers(json.dumps([{"type": "outline", "color": "#ff0000", "width": 0.01, "style": "solid"},
                                      {"type": "effect", "kind": "grid", "target": "background", "color": "#00ff00", "spacing": 0.1, "amount": 1},
                                      {"type": "effect", "kind": "chromatic", "start": 3.0, "end": 3.5},
                                      {"type": "track", "anchor": "subject_top", "label": "LOOK", "emoji": "\U0001F525", "shape": "ring", "color": "#0000ff"}]), 4.0)
    with pytest.raises(MajoorError, match="mask"):
        render_motion(video, layers, tmp_path / "no.mp4")
    out = tmp_path / "fx.mp4"
    render_motion(video, layers, out, masks=_masks())
    f = _frame(out, 1.0)
    red = (f[..., 0] > 200) & (f[..., 1] < 80) & (f[..., 2] < 80)
    ys, xs = np.nonzero(red)
    assert len(xs) > 100 and xs.min() < 110 and xs.max() > 209  # the contour surrounds the rectangle of the subject
    green = (f[..., 1] > f[..., 0] + 20) & (f[..., 1] > f[..., 2] + 20)
    assert green[:, :100].any() and not green[80:160, 125:195].any()  # grid on the background only
    assert (f[..., 2] > 180).any()  # the ring of the tracked point


def test_track_follows_a_moving_point_and_emoji_renders(video, tmp_path):
    layers = parse_layers(json.dumps([{"type": "track", "at": [0.5, 0.5], "shape": "dot", "color": "#ff00ff"}, {"type": "emoji", "content": "\U0001F525", "position": "top_right", "size": 0.2},
                                      {"type": "effect", "kind": "glitch", "amount": 1, "start": 1, "end": 1.4}, {"type": "effect", "kind": "dots"}, {"type": "effect", "kind": "scanlines", "flicker": 4}]), 4.0)
    out = tmp_path / "tr.mp4"
    render_motion(video, layers, out)
    assert probe(out, with_packets=False).frame_count == 96


def test_the_contour_glides_between_two_masks_and_the_edge_is_smooth():
    from majoor_videotools.core.motion import Masks

    masks = np.zeros((2, 100, 100), np.float32)
    masks[0, 20:60, 10:40] = 1  # the subject on the left...
    masks[1, 20:60, 60:90] = 1  # ...then on the right
    m = Masks(masks)
    first, early, middle, last = (m.at(i, 11, 100, 100) for i in (0, 2, 5, 10))
    assert first[40, 25] > 0.9 and first[40, 75] < 0.1 and last[40, 75] > 0.9 and last[40, 25] < 0.1  # the first and the last mask are the first and the last frame
    assert early[40, 25] > 0.7 and early[40, 75] < 0.3  # the weight of the second mask grows with the frame
    assert middle[40, 25] > 0.3 and middle[40, 75] > 0.3  # in between, both shapes are there: the contour glides between them
    edge = first[40, :]
    assert ((edge > 0.05) & (edge < 0.95)).sum() >= 2  # a row across the edge: values between 0 and 1, not a step
    assert Masks(None).at(0, 10, 10, 10) is None
