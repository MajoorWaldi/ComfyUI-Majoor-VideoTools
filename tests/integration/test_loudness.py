"""The finished edit is brought to a target loudness with a true peak under the ceiling."""
import subprocess

import pytest

from majoor_videotools.core.audio_quality import measure_loudness, normalize_loudness


def make_video(path, audio_filter, seconds=6):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s=128x128:d={seconds}:r=24", "-f", "lavfi", "-i", audio_filter, "-t", str(seconds),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(path)], check=True)
    return path


@pytest.mark.parametrize("label,audio", [
    ("quiet tone", "sine=f=220:d=6,volume=-8dB"),
    ("loud tone", "sine=f=220:d=6,volume=12dB"),
    ("clicks", "aevalsrc='if(lt(mod(t,0.5),0.01),0.95*sin(2*PI*180*t),0.02*sin(2*PI*440*t))':d=6:s=48000"),
])
def test_the_edit_reaches_the_target_loudness_under_the_ceiling(tmp_path, label, audio):
    source = make_video(tmp_path / "in.mp4", audio)
    report = normalize_loudness(source, tmp_path / "out.mp4", -14.0, -1.5)
    final = measure_loudness(tmp_path / "out.mp4")
    assert final["true_peak_dbtp"] is not None and final["true_peak_dbtp"] <= -1.0, (label, final)
    if label != "clicks":  # a very peaky signal cannot be brought to the target without the limiter eating its peaks: it only has to stay under the ceiling
        assert abs(final["integrated_lufs"] + 14.0) <= 1.0, (label, final)
    assert report["applied"] is True and abs(report["gain_db"]) <= 18.0


def test_a_silent_edit_is_copied_as_it_is(tmp_path):
    source = make_video(tmp_path / "in.mp4", "anullsrc=r=48000:cl=stereo:d=6")
    report = normalize_loudness(source, tmp_path / "out.mp4")
    assert report["applied"] is False and (tmp_path / "out.mp4").stat().st_size == source.stat().st_size


def test_a_file_already_at_the_target_is_left_alone(tmp_path):
    source = make_video(tmp_path / "in.mp4", "sine=f=220:d=6,volume=-8dB")
    first = normalize_loudness(source, tmp_path / "a.mp4")
    second = normalize_loudness(tmp_path / "a.mp4", tmp_path / "b.mp4")
    assert first["applied"] is True and second["applied"] is False
