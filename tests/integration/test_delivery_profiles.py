import json
import subprocess
from dataclasses import replace

import numpy as np
import pytest

from majoor_videotools.core.assembler import AssemblyOptions, assemble_shots
from majoor_videotools.core.delivery_profiles import PROFILES, video_stream
from majoor_videotools.core.errors import AssemblyError
from majoor_videotools.core.media_probe import probe
from majoor_videotools.core.paths import ProjectStore
from majoor_videotools.core.scene_detection import detect_scenes


@pytest.fixture
def ramp(tmp_path):
    source = tmp_path / "ramp.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "nullsrc=s=1024x128:r=24:d=1,format=yuv444p10le,geq=lum='64+876*X/1023':cb=512:cr=512,"
                    "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709",
                    "-c:v", "ffv1", "-color_range", "tv", "-colorspace", "bt709",
                    "-color_trc", "bt709", "-color_primaries", "bt709", str(source)], check=True)
    root = tmp_path / "projects"
    shots = detect_scenes(source, root, "manual", .5, 1, thumbnails=False)
    return shots, root


def decode_luma(path):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1",
                                   "-vf", "extractplanes=y", "-pix_fmt", "gray10le", "-f", "rawvideo", "-"])
    return np.frombuffer(raw, dtype="<u2").reshape(128, 1024)


@pytest.mark.parametrize("name", ["prores_422_hq", "dnxhr_hqx", "prores_4444"])
def test_master_keeps_real_ten_bit_ramp_frames_and_metadata(ramp, name):
    shots, root = ramp
    result = assemble_shots(shots, root, AssemblyOptions(audio_policy="mute", delivery_profile=name, output_format="mov"))
    stream = video_stream(result.path)
    assert stream["codec_name"] == PROFILES[name].codec
    assert stream["pix_fmt"] in PROFILES[name].decoded_formats
    assert stream.get("color_range") in (None, "unknown", "tv") if stream["codec_name"] == "prores" else stream["color_range"] == "tv"
    assert all(stream[key] == "bt709" for key in ("color_space", "color_transfer", "color_primaries"))
    assert probe(result.path).frame_count == 24
    luma = decode_luma(result.path)
    assert len(np.unique(luma[64])) > 512  # An 8-bit intermediate cannot satisfy this.
    expected = 64 + 876 * np.arange(1024) / 1023
    assert np.abs(luma[64].astype(float) - expected).max() < 5
    assert result.path.stat().st_size > 0
    again = assemble_shots(shots, root, AssemblyOptions(audio_policy="mute", delivery_profile=name, output_format="mov"))
    assert again.reused and again.path == result.path
    metadata = json.loads(result.path.with_name(result.path.name + ".delivery.json").read_text())
    assert metadata["delivery_profile"] == name
    assert metadata["signal_range"] == "limited"
    scripts = list(ProjectStore(root, shots.project_id).resolve("logs").glob("filter_*.txt"))
    assert all("yuv420p" not in path.read_text() for path in scripts)


def test_legacy_social_profile_is_unchanged(ramp):
    shots, root = ramp
    result = assemble_shots(shots, root, AssemblyOptions(audio_policy="mute"))
    stream = video_stream(result.path)
    assert stream["codec_name"] == "h264" and stream["pix_fmt"] == "yuv420p"
    assert result.path.suffix == ".mp4"


def test_master_requires_explicit_container_before_media_io(tmp_path):
    with pytest.raises(AssemblyError, match="requires output_format=mov"):
        assemble_shots(None, tmp_path, AssemblyOptions(delivery_profile="prores_422_hq"))


def test_master_does_not_infer_color_or_convert_hdr(ramp, monkeypatch):
    from majoor_videotools.core import delivery_profiles
    shots, root = ramp
    original = delivery_profiles.video_stream
    def untagged(path):
        return {key: value for key, value in original(path).items()
                if key not in ("color_space", "color_transfer", "color_primaries")}
    monkeypatch.setattr(delivery_profiles, "video_stream", untagged)
    with pytest.raises(AssemblyError, match="missing color"):
        assemble_shots(shots, root, AssemblyOptions(delivery_profile="prores_422_hq", output_format="mov"))
    monkeypatch.setattr(delivery_profiles, "video_stream", lambda path: {**original(path), "color_transfer": "smpte2084"})
    with pytest.raises(AssemblyError, match="incompatible"):
        assemble_shots(shots, root, AssemblyOptions(delivery_profile="prores_422_hq", output_format="mov", color_policy="assume_bt709"))


def test_prores_4444_preserves_nonconstant_alpha(tmp_path):
    source = tmp_path / "alpha.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "nullsrc=s=256x128:r=24:d=1,format=yuva444p10le,geq=lum=512:cb=512:cr=512:a='1023*X/255',"
                    "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709",
                    "-c:v", "ffv1", "-color_range", "tv", "-colorspace", "bt709",
                    "-color_trc", "bt709", "-color_primaries", "bt709", str(source)], check=True)
    root = tmp_path / "projects"
    shots = detect_scenes(source, root, "manual", .5, 1, thumbnails=False)
    result = assemble_shots(shots, root, AssemblyOptions(audio_policy="mute", delivery_profile="prores_4444", output_format="mov"))
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(result.path), "-frames:v", "1",
                                   "-vf", "alphaextract", "-pix_fmt", "gray16le", "-f", "rawvideo", "-"])
    alpha = np.frombuffer(raw, dtype="<u2").reshape(128, 256)
    assert alpha[64, 0] < 256 and alpha[64, -1] > 65000
    assert len(np.unique(alpha[64])) > 240
