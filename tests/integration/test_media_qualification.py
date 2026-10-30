"""Generated fixtures only. These checks do not qualify a real H3/YuE2 run."""
import subprocess
from fractions import Fraction

import pytest
import numpy as np

from majoor_videotools.core.assembler import AssemblyOptions, assemble_shots
from majoor_videotools.core.media_probe import probe
from majoor_videotools.core.scene_detection import detect_scenes


@pytest.mark.parametrize("fps", ["24", "25", "30", "24000/1001", "30000/1001"])
def test_cfr_assembly_preserves_frame_count_and_duration(tmp_path, fps):
    source = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=128x96:r={fps}",
                    "-frames:v", "48", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)], check=True)
    root = tmp_path / "projects"
    shot_list = detect_scenes(source, root, "manual", .5, 1, cut_points="24", thumbnails=False)
    result = assemble_shots(shot_list, root, AssemblyOptions(audio_policy="mute", effects=False))
    actual = probe(result.path)
    assert actual.frame_count == 48
    assert actual.fps == Fraction(fps)
    assert actual.duration == Fraction(48) / Fraction(fps)
    assert not actual.has_audio


@pytest.mark.parametrize("rotation", [90, 270])
def test_rotation_metadata_is_baked_into_display_dimensions(tmp_path, rotation):
    base, source = tmp_path / "base.mp4", tmp_path / "rotated.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=128x96:r=24:d=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(base)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-display_rotation:v:0", str(rotation),
                    "-i", str(base), "-c", "copy", str(source)], check=True)
    expected = probe(source)
    assert expected.rotation % 180 == 90
    root = tmp_path / "projects"
    shot_list = detect_scenes(source, root, "manual", .5, 1, thumbnails=False)
    result = assemble_shots(shot_list, root, AssemblyOptions(audio_policy="mute", effects=False))
    actual = probe(result.path)
    assert actual.display_size == expected.display_size
    assert actual.rotation == 0
    assert actual.frame_count == 24


def test_late_take_audio_keeps_its_offset_against_picture(tmp_path):
    source = tmp_path / "delayed.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:s=128x96:r=24:d=2",
                    "-itsoffset", "0.25", "-f", "lavfi", "-i", "sine=f=880:r=48000:d=1.75",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(source)], check=True)
    root = tmp_path / "projects"
    shots = detect_scenes(source, root, "manual", .5, 1, thumbnails=False)
    result = assemble_shots(shots, root, AssemblyOptions(audio_policy="shot_audio", effects=False))
    audio = np.frombuffer(subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(result.path),
                          "-vn", "-ac", "1", "-af", "aresample=8000:first_pts=0", "-f", "f32le", "-"]), dtype="<f4")
    assert np.sqrt(np.mean(audio[400:1200] ** 2)) < .002
    assert np.sqrt(np.mean(audio[2800:4000] ** 2)) > .05


def test_nonzero_pts_and_multiple_audio_tracks_keep_first_track(tmp_path):
    source = tmp_path / "offset.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=128x96:r=24:d=2",
                    "-f", "lavfi", "-i", "sine=f=440:r=48000:d=2", "-f", "lavfi", "-i", "sine=f=880:r=48000:d=2",
                    "-map", "0:v", "-map", "1:a", "-map", "2:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "pcm_s16le", "-output_ts_offset", "7", str(source)], check=True)
    assert probe(source).first_pts > 0
    root = tmp_path / "projects"
    shots = detect_scenes(source, root, "manual", .5, 1, thumbnails=False)
    result = assemble_shots(shots, root, AssemblyOptions(audio_policy="shot_audio", effects=False))
    info = probe(result.path)
    assert info.first_pts == 0 and info.frame_count == 48
    audio = np.frombuffer(subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(result.path),
                          "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"]), dtype="<f4")
    window = audio[800:7200]
    measured = np.argmax(abs(np.fft.rfft(window))) * 8000 / len(window)
    assert abs(measured - 440) < 5
