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


def test_a_calm_brief_does_not_force_the_loud_drop():
    music=_track(120,40,drop_at=16.2)
    _,calm=fit_music(music,RATE,6,energy_goal='calm')
    _,intense=fit_music(music,RATE,6,energy_goal='intense')
    assert calm['start']+6<16.2
    assert intense['start']>=16.1
    assert calm['energy_goal']=='calm'


def test_requested_reveal_prefers_a_window_with_an_accent_near_that_time():
    music=_track(120,40,drop_at=100)
    start=int(24.2*RATE);n=int(.15*RATE)
    kick=.9*np.sin(2*np.pi*55*np.arange(n)/RATE)*np.exp(-np.arange(n)/(.04*RATE))
    music[start:start+n]+=kick[:,None]
    _,info=fit_music(music,RATE,6,bpm=120,moments=[{'at':2,'strength':1}])
    assert abs(info['start']+2-24.2)<.15
    assert info['accent_matches'][0]['error_seconds']<.15


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


def test_kept_music_is_read_back_as_it_was_written(tmp_path):
    import numpy as np

    from majoor_videotools.core.beats import read_wav, write_wav

    samples = (np.sin(np.linspace(0, 400, 4800)) * 0.5).astype(np.float32)
    stereo = np.stack([samples, samples * 0.5], axis=1)
    write_wav(tmp_path / "music.wav", stereo, 24000)
    back, rate = read_wav(tmp_path / "music.wav")
    assert rate == 24000 and back.shape == (4800, 2) and np.abs(back - stereo).max() < 1e-3


def test_loop_selection_uses_energy_intent_and_keeps_manual_start():
    music = _track(120, 10, drop_at=4.2)
    calm, ci = fit_music(music, RATE, 14, bpm=120, energy_goal='calm')
    intense, ii = fit_music(music, RATE, 14, bpm=120, energy_goal='intense')
    assert ci['looped'] and ii['looped'] and ii['start'] > ci['start']
    _, manual = fit_music(music, RATE, 14, bpm=120, energy_goal='intense', start=.2)
    assert abs(manual['start']-.2) < .1
    assert calm.shape == intense.shape == (14*RATE, 2)
