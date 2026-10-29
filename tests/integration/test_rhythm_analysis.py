import numpy as np
import pytest

from majoor_videotools.core.beats import analyze_rhythm, detect_beats
from majoor_videotools.core.music_fit import fit_music
from majoor_videotools.core.timeline_sources import plan_from_music


def test_silence_is_not_a_measured_grid_but_user_tempo_remains_intentional():
    silence = np.zeros(8 * 16000, np.float32)
    result = analyze_rhythm(silence, 16000)
    assert result['bpm'] is None and result['timing_source'] == 'none'
    assert len(result['beats']) == 0 and result['tempo_confidence'] == 0
    assert detect_beats(silence, 16000)[0] == 0
    given = analyze_rhythm(silence, 16000, 120)
    assert given['bpm'] == 120 and given['timing_source'] == 'user_grid'
    assert len(given['beats']) == 16 and given['phase_confidence'] == 0


def test_nonrhythmic_music_remains_usable_without_invented_bar_cuts():
    out, info = fit_music(np.zeros((16 * 16000, 2), np.float32), 16000, 8)
    assert out.shape == (8 * 16000, 2)
    assert info['bpm'] is None and info['timing_source'] == 'none'
    plan, detail = plan_from_music(np.zeros(8 * 16000), 16000, shots=3)
    assert len(plan['shots']) == 3
    assert sum(row['duration_frames'] for row in plan['shots']) == 192
    assert detail['timing_source'] == 'none'


def test_impulse_train_and_input_validation():
    rate = 16000
    samples = np.zeros(rate * 8, np.float32)
    for start in np.arange(.2, 8, .5):
        i = int(start * rate)
        samples[i:i + 80] = np.hanning(80)
    result = analyze_rhythm(samples, rate)
    assert result['timing_source'] == 'measured'
    assert abs(result['bpm'] - 120) < 2 and result['tempo_confidence'] > .15
    for values, sample_rate in [(np.array([np.nan]), rate), (samples, 0)]:
        with pytest.raises(ValueError):
            analyze_rhythm(values, sample_rate)
    assert analyze_rhythm(np.zeros(10), rate)['bpm'] is None


def test_nonpulse_window_keeps_both_existing_edge_fades(monkeypatch):
    from majoor_videotools.core import music_fit
    monkeypatch.setattr(music_fit,'analyze_rhythm',lambda *a:{'bpm':None,'beats':np.zeros(0)})
    samples=np.full((16000*5,2),.15,np.float32)
    result,_=music_fit.fit_music(samples,16000,2,start=1)
    assert result[0,0]==0 and result[-1,0]==0
    assert result[100,0]>.1
