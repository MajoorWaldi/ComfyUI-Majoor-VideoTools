import subprocess

import pytest

from majoor_videotools.core.audio_quality import assess_loudness, measure_loudness, normalize_loudness
from test_loudness import make_video


def test_assessment_does_not_call_a_dynamic_off_target_mix_compliant():
    result = assess_loudness({'integrated_lufs': -18, 'true_peak_dbtp': -2})
    assert result['status'] == 'warning' and not result['within_target'] and result['within_ceiling']


def test_video_without_audio_is_preserved(tmp_path):
    source = tmp_path / 'silent.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=s=64x64:d=1', str(source)], check=True)
    out = tmp_path / 'out.mp4'
    report = normalize_loudness(source, out)
    assert source.read_bytes() == out.read_bytes()
    assert report['assessment']['status'] == 'not_evaluated'


@pytest.mark.parametrize('audio', [
    "sine=f=18000:r=48000:d=6,volume=18dB",
    "aevalsrc='if(lt(mod(t,1),0.005),0.99*sin(2*PI*997*t),0.001*sin(2*PI*440*t))':d=6:s=48000",
])
def test_decoded_aac_peak_has_priority_over_loudness_target(tmp_path, audio):
    source = make_video(tmp_path / 'in.mp4', audio)
    report = normalize_loudness(source, tmp_path / 'out.mp4')
    measured = measure_loudness(tmp_path / 'out.mp4')
    assert measured['true_peak_dbtp'] <= -1.5
    assert report['assessment']['within_ceiling']


def test_non_finite_normalization_parameters_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        normalize_loudness(tmp_path / 'missing.mp4', tmp_path / 'out.mp4', float('nan'))
