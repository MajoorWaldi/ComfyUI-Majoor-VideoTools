import wave

import numpy as np

from majoor_videotools.core.audio_quality import measure_true_peak


def test_true_peak_measures_a_controlled_tone(tmp_path):
    path=tmp_path/'tone.wav'
    tone=(np.sin(np.arange(48000)*2*np.pi*1000/48000)*.5*32767).astype('<i2')
    with wave.open(str(path),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(48000);out.writeframes(tone.tobytes())
    report=measure_true_peak(path)
    assert -6.2<report['true_peak_dbtp']<-5.8
    assert report['within_ceiling']
