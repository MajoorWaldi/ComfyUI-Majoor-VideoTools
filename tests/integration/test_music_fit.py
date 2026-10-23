import numpy as np
import pytest

from majoor_videotools.core.beats import detect_beats
from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.music_fit import fit_music

RATE = 44100


def _track(bpm, seconds, drop_at, offset=0.2):
    """A quiet intro then a drop: a kick on every beat, the one that starts a bar stronger."""
    period = 60 / bpm
    x = np.zeros(int(seconds * RATE), np.float32)
    for k in range(int((seconds - offset) / period)):
        t = offset + k * period
        s = int(t * RATE)
        n = int(0.15 * RATE)
        gain = (0.8 if t >= drop_at else 0.05) * (1.0 if k % 4 == 0 else 0.55)  # the first beat of a bar hits hardest
        kick = gain * np.sin(2 * np.pi * 55 * np.arange(n) / RATE) * np.exp(-np.arange(n) / (0.04 * RATE))
        x[s:s + n] += kick[: len(x) - s]
    return np.stack([x, x], axis=1)


def test_the_window_starts_on_the_drop_and_on_a_downbeat():
    bpm = 128
    period = 60 / bpm
    music = _track(bpm, 40, drop_at=0.2 + 8 * 4 * period / 2)  # the drop is on a bar, 4 bars in
    out, info = fit_music(music, RATE, 8.0)
    assert out.shape == (8 * RATE, 2)
    assert abs(info["bpm"] - bpm) < 1.5 and not info["looped"]
    drop = 0.2 + 16 * period
    assert info["start"] >= drop - 0.05  # never the quiet intro
    assert abs(((info["start"] - 0.2) / (4 * period)) - round((info["start"] - 0.2) / (4 * period))) < 0.03  # on a bar
    assert abs(out[: int(0.5 * RATE)]).max() > 0.3  # it starts with the kick, not a silence


def test_a_start_is_snapped_to_a_bar_and_a_short_music_is_looped():
    music = _track(120, 30, drop_at=0.0)
    out, info = fit_music(music, RATE, 5.0, start=7.0)
    assert abs(info["start"] - 7.0) < 4 * 60 / 120
    short, looped = fit_music(_track(120, 6, drop_at=0.0), RATE, 14.0)
    assert looped["looped"] and short.shape == (14 * RATE, 2) and abs(short).max() > 0.3
    assert abs(short[-RATE:]).max() > 0.3 or abs(short[-3 * RATE:-RATE]).max() > 0.3  # the loop goes on to the end
    with pytest.raises(MajoorError, match="too short"):
        fit_music(np.zeros((RATE, 2), np.float32), RATE, 4.0)
    with pytest.raises(MajoorError, match="above 0"):
        fit_music(music, RATE, 0.0)


def test_the_cut_music_has_its_beats_on_the_cuts_grid():
    music = _track(140, 30, drop_at=0.0, offset=0.37)
    out, info = fit_music(music, RATE, 8.0)
    found, beats = detect_beats(out.mean(axis=1), RATE)
    assert abs(found - 140) < 2
    assert abs(beats[0] - 0.02) < 0.04 or abs(beats[0] - (0.02 + 60 / 140)) < 0.04  # the downbeat is at the pre-roll
