import copy
import json
import shutil
import subprocess

import numpy as np
import pytest

from majoor_videotools.core.assembler import AssemblyOptions, assemble_shots
from majoor_videotools.core.dialogue import lines_of_shot
from majoor_videotools.core.dialogue_track import audio_preview, render_dialogue
from majoor_videotools.core.errors import AssemblyError, ManifestError, MajoorError
from majoor_videotools.core.media_probe import probe
from majoor_videotools.core.models import Detection, Revision, Shot, ShotList, Source
from majoor_videotools.core.paths import ProjectStore
from majoor_videotools.core.timeline_edit import compile_edit, initial_document, parse_document


@pytest.fixture
def dialogue_project(tmp_path):
    root = tmp_path / "projects"
    store = ProjectStore(root, "p_12345678")
    media = store.resolve("generated/voice.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:s=64x64:r=24:d=4",
                    "-f", "lavfi", "-i", "aevalsrc=0.2*sin(2*PI*(330*t+90*t*t)):s=48000:d=4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(media)], check=True)
    shutil.copyfile(media, store.resolve("sources/source.mp4"))
    src = Source("sources/source.mp4", "fixture", 64, 64, 24, 1, "CFR", 96, 4, True)
    take = Revision("take_001", "generated/voice.mp4", 4, "generated")
    shots = tuple(Shot(f"S{i}", i, i * 24, (i + 1) * 24, None, None, 1, src.uri, take.revision_id,
                       (Revision("original", src.uri, 1, "original", media_range={"start_frame": i * 24}), take),
                       plan={"fx": {"speed": 2, "sub_cuts": [{"frames": 12}, {"frames": 12, "start": 0}]}})
                  for i in range(3))
    sl = ShotList(store.dir.name, src, Detection("manual", .5, 1, "fixture"), shots)
    store.write_json("manifest.json", sl.to_dict())
    return root, store, sl


def decode(path):
    return np.frombuffer(subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path),
                         "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"]), dtype=np.float32)


def test_full_timed_sentence_is_not_clamped_or_repeated_at_a_picture_cut():
    lines = '0.5-2.8 s: Finish the whole sentence.\n2.9-4 s: Next sentence.'
    assert lines_of_shot("", lines, 0, 1) == "0.50-2.80 s: Finish the whole sentence."
    assert lines_of_shot("", lines, 1, 2) == ""
    assert lines_of_shot("", lines, 2, 3) == "0.90-2.00 s: Next sentence."


def test_audio_bounds_compile_and_old_documents_remain_unchanged(dialogue_project):
    _, _, sl = dialogue_project
    before = sl.to_dict()
    doc = initial_document(sl)
    assert "dialogue" not in doc
    assert all("dialogue_track" not in s.plan for s in compile_edit(sl, doc).shots)
    doc["dialogue"] = [{**doc["clips"][0], "id": "voice", "in_frame": 6, "out_frame": 66, "at_frame": 6, "gain": .5}]
    doc["music_gain"] = .3
    result = compile_edit(sl, doc)
    assert result.shots[0].plan["dialogue_track"] == [
        {"file": "generated/voice.mp4", "start": .25, "duration": 2.5, "at": .25, "gain": .5}]
    assert result.shots[0].plan["timeline_music_gain"] == .3
    assert parse_document(sl, json.dumps(doc)) == doc
    for update in ({"in_frame": True}, {"out_frame": 97}, {"at_frame": -1},
                   {"gain": float("nan")}, {"gain": 1.1}, {"revision_id": "../../voice"}):
        broken = copy.deepcopy(doc)
        broken["dialogue"][0].update(update)
        with pytest.raises(MajoorError):
            compile_edit(sl, broken)
    assert sl.to_dict() == before


def test_original_source_dialogue_can_cross_its_detected_shot_boundary(dialogue_project):
    root, _, sl = dialogue_project
    doc = initial_document(sl)
    doc["dialogue"] = [{**doc["clips"][1], "id": "original_voice", "revision_id": "original",
                        "in_frame": 0, "out_frame": 48, "at_frame": 0}]
    edited = compile_edit(sl, doc)
    assert edited.shots[0].plan["dialogue_track"][0] == {
        "file": "sources/source.mp4", "start": 1., "duration": 2., "at": 0., "gain": 1.}
    result = assemble_shots(edited, root, AssemblyOptions(audio_policy="shot_audio"))
    audio = decode(result.path)
    for second in (.5, 1.5):
        part = audio[round(second * 48000):round((second + .1) * 48000)]
        frequency = np.argmax(abs(np.fft.rfft(part * np.hanning(len(part))))) * 48000 / len(part)
        assert abs(frequency - (330 + 180 * (second + 1.05))) < 14
    doc["dialogue"][0]["out_frame"] = 73
    with pytest.raises(ManifestError):
        compile_edit(sl, doc)


def test_independent_dialogue_survives_two_picture_cuts_and_cache_reuses(dialogue_project):
    root, store, sl = dialogue_project
    manifest = store.resolve("manifest.json").read_bytes()
    doc = initial_document(sl)
    doc["clips"].reverse()
    for clip in doc["clips"]:
        clip.update(in_frame=24, out_frame=48)
    doc["dialogue"] = [{**doc["clips"][0], "id": "voice", "in_frame": 6, "out_frame": 66, "at_frame": 6, "gain": .5}]
    edited = compile_edit(sl, doc)
    result = assemble_shots(edited, root, AssemblyOptions(audio_policy="shot_audio"))
    assert probe(result.path).frame_count == 72
    samples = decode(result.path)
    assert np.sqrt(np.mean(samples[1000:8000] ** 2)) < .001  # No duplicated visual-take audio.
    for second in (.5, .95, 1.05, 1.5, 1.95, 2.05, 2.5):
        chunk = samples[round((second - .04) * 48000):round((second + .04) * 48000)]
        measured = np.argmax(abs(np.fft.rfft(chunk * np.hanning(len(chunk))))) * 48000 / len(chunk)
        assert abs(measured - (330 + 180 * second)) < 14, (second, measured)
        assert .05 < np.sqrt(np.mean(chunk ** 2)) < .09
    assert np.sqrt(np.mean(samples[round(2.85 * 48000):] ** 2)) < .001
    assert assemble_shots(edited, root, AssemblyOptions(audio_policy="shot_audio")).reused
    assert store.resolve("manifest.json").read_bytes() == manifest
    doc["dialogue"][0]["gain"] = .25
    quieter = assemble_shots(compile_edit(sl, doc), root, AssemblyOptions(audio_policy="shot_audio"))
    assert quieter.path != result.path
    assert np.sqrt(np.mean(decode(quieter.path) ** 2)) < .6 * np.sqrt(np.mean(samples ** 2))
    preview = audio_preview(store, "generated/voice.mp4")
    assert preview["duration"] >= 4 and len(preview["peaks"]) == 512
    assert store.resolve(preview["file"]).is_file()


def test_end_overflow_is_never_silently_truncated_and_empty_track_mutes_takes(dialogue_project):
    root, store, sl = dialogue_project
    doc = initial_document(sl)
    doc["dialogue"] = [{**doc["clips"][0], "id": "voice", "out_frame": 96, "at_frame": 0}]
    with pytest.raises(ManifestError, match="beyond the video"):
        assemble_shots(compile_edit(sl, doc), root, AssemblyOptions(audio_policy="shot_audio"))
    doc["dialogue"][0]["gain"] = 0
    muted = assemble_shots(compile_edit(sl, doc), root, AssemblyOptions(audio_policy="shot_audio"))
    assert np.max(abs(decode(muted.path))) < 1e-5
    doc["dialogue"] = []
    empty = assemble_shots(compile_edit(sl, doc), root, AssemblyOptions(audio_policy="shot_audio"))
    assert np.max(abs(decode(empty.path))) < 1e-5
    with pytest.raises(AssemblyError, match="cannot retime"):
        assemble_shots(sl, root, AssemblyOptions(audio_policy="shot_audio", preserve_dialogue=True, duration_policy="retime_to_target"))
    with pytest.raises(ManifestError, match="beyond the video"):
        assemble_shots(sl, root, AssemblyOptions(audio_policy="shot_audio", preserve_dialogue=True))
    with pytest.raises(MajoorError, match="escapes"):
        render_dialogue(store, [{"file": "../../outside", "start": 0, "duration": 1, "at": 0, "gain": 1}], 3)


def test_music_volume_and_optional_ducking_use_independent_dialogue_bus(dialogue_project):
    root, store, sl = dialogue_project
    music = store.resolve("music/test.wav")
    music.parent.mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=3",
                    str(music)], check=True)
    doc = initial_document(sl)
    doc["dialogue"] = [{**doc["clips"][0], "id": "voice", "in_frame": 6, "out_frame": 66, "at_frame": 6}]
    edited = compile_edit(sl, doc)
    raw_mix = decode(assemble_shots(edited, root, AssemblyOptions(audio_policy="mute", music=music, music_fade=0)).path)
    ducked = decode(assemble_shots(edited, root, AssemblyOptions(audio_policy="mute", music=music, music_fade=0, duck=1.)).path)

    def music_level(samples, at):
        chunk = samples[round(at * 48000):round((at + .15) * 48000)]
        return abs(np.fft.rfft(chunk * np.hanning(len(chunk))))[33]  # 220 Hz, 33 cycles.

    assert music_level(ducked, 1.5) < .7 * music_level(raw_mix, 1.5)
    doc["music_gain"] = .25
    quiet = decode(assemble_shots(compile_edit(sl, doc), root, AssemblyOptions(audio_policy="mute", music=music)).path)
    assert .20 < music_level(quiet, .02) / music_level(raw_mix, .02) < .3
    bus = render_dialogue(store, [{"file": "generated/voice.mp4", "start": .25, "duration": 2.5, "at": .25, "gain": 1.}], 3.)
    explicit = assemble_shots(compile_edit(sl, initial_document(sl)), root, AssemblyOptions(audio_policy="shot_audio", dialogue=bus))
    assert np.sqrt(np.mean(decode(explicit.path)[1000:8000] ** 2)) < .001


def test_automatic_voice_protection_preserves_full_audio_and_source_plans(dialogue_project):
    root, store, sl = dialogue_project
    before = sl.to_dict()
    manifest = store.resolve("manifest.json").read_bytes()
    result = assemble_shots(sl, root, AssemblyOptions(audio_policy="shot_audio", preserve_dialogue=True,
                                                     duration_policy="use_generated_duration"))
    assert result.duration_seconds == 12 and probe(result.path).frame_count == 288
    assert any("Dialogue protected" in warning for warning in result.warnings)
    samples = decode(result.path)
    for second in (1.5, 5.5, 9.5):
        part = samples[round(second * 48000):round((second + .1) * 48000)]
        frequency = np.argmax(abs(np.fft.rfft(part * np.hanning(len(part))))) * 48000 / len(part)
        assert abs(frequency - (330 + 180 * (1.55))) < 14
    assert sl.to_dict() == before
    assert store.resolve("manifest.json").read_bytes() == manifest
    bus = render_dialogue(store, [{"file": shot.active.media_ref, "start": 0., "duration": 4.,
                                  "at": i * 4., "gain": 1.} for i, shot in enumerate(sl.shots)], 12.)
    explicit = assemble_shots(sl, root, AssemblyOptions(audio_policy="shot_audio", dialogue=bus,
                                                       duration_policy="use_generated_duration"))
    assert probe(explicit.path).frame_count == 288
