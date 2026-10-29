import dataclasses
import json
import subprocess

import numpy as np
import pytest

from majoor_videotools.core.assembler import AssemblyOptions, assemble_shots
from majoor_videotools.core.errors import AssemblyError, ManifestError, ShotNotFoundError
from majoor_videotools.core.media_probe import probe
from majoor_videotools.core.models import Detection, Revision, Shot, ShotList, Source
from majoor_videotools.core.paths import ProjectStore
from majoor_videotools.core.timeline_edit import compile_edit, initial_document, parse_document, source_signature


@pytest.fixture
def source_list():
    source = Source("sources/source.mp4", "source-fingerprint", 128, 128, 24, 1, "CFR", 120, 5, True)
    shots = []
    for i in range(5):
        original = Revision("original", source.uri, 1, "original", media_range={"start_frame": i * 24})
        take = Revision("take_001", f"generated/{i}.mp4", 3, "generated", fingerprint=str(i),
                        duration_policy="keep_generated", generation_prompt=f"Prompt {i}")
        shots.append(Shot(f"SHOT_{i + 1}", i, i * 24, (i + 1) * 24, None, None, 1,
                          source.uri, "take_001", (original, take),
                          plan={"prompt": "Correction", "fx": {"speed": 2}, "motion": [{"text": "old timing"}]}))
    return ShotList("p_12345678", source, Detection("manual", .5, 1, "key"), tuple(shots))


def test_reorder_cut_duplicate_trim_are_derived_and_roundtrip(source_list):
    before = source_list.to_dict()
    document = initial_document(source_list)
    assert all(c["out_frame"] == 72 for c in document["clips"])
    document["clips"] = [document["clips"][i] for i in (0, 3, 1, 2, 4)]
    first = document["clips"][0]
    first["out_frame"] = 12
    document["clips"].insert(1, {**first, "id": "second_half", "in_frame": 12, "out_frame": 24})
    document["clips"].append({**first, "id": "duplicate"})
    result = compile_edit(source_list, document)
    assert [s.plan["timeline_edit"]["source_shot_id"] for s in result.shots] == [
        "SHOT_1", "SHOT_1", "SHOT_4", "SHOT_2", "SHOT_3", "SHOT_5", "SHOT_1"]
    assert result.shots[1].active.source_start_seconds == .5
    assert result.shots[1].active.media_ref == result.shots[0].active.media_ref
    assert result.shots[0].active.generation_prompt == "Prompt 0"
    assert all("fx" not in s.plan and "motion" not in s.plan for s in result.shots)
    assert len({s.shot_id for s in result.shots}) == 7
    assert source_list.to_dict() == before
    assert ShotList.from_dict(result.to_dict()) == result
    assert parse_document(source_list, json.dumps(document)) == document


@pytest.mark.parametrize("change", [
    lambda d: d.update(version=2),
    lambda d: d.update(project_id="p_00000000"),
    lambda d: d.update(source_signature="stale"),
    lambda d: d.update(fps_num=30),
    lambda d: d.update(fps_den=True),
    lambda d: d.update(clips=[]),
    lambda d: d["clips"][0].update(in_frame=-1),
    lambda d: d["clips"][0].update(in_frame=True),
    lambda d: d["clips"][0].update(in_frame=.5),
    lambda d: d["clips"][0].update(out_frame=73),
    lambda d: d["clips"][0].update(out_frame=0),
    lambda d: d["clips"][0].update(id="../escape"),
    lambda d: d["clips"][1].update(id=d["clips"][0]["id"]),
    lambda d: d["clips"][0].update(revision_id="missing"),
    lambda d: d["clips"][0].update(shot_id="missing"),
])
def test_invalid_edits_are_explicit_errors(source_list, change):
    document = initial_document(source_list)
    change(document)
    with pytest.raises((ManifestError, ShotNotFoundError)):
        compile_edit(source_list, document)


def test_changed_take_is_not_silently_rebased(source_list):
    document = initial_document(source_list)
    shot = source_list.shots[0]
    changed = dataclasses.replace(shot.active, fingerprint="changed-file")
    new_list = source_list.with_shot(dataclasses.replace(shot, revisions=(shot.revisions[0], changed)))
    assert source_signature(new_list) != document["source_signature"]
    with pytest.raises(ManifestError, match="sources or takes changed"):
        compile_edit(new_list, document)


def test_original_offsets_are_not_replaced_by_editorial_positions(source_list):
    document = initial_document(source_list)
    document["clips"] = [{**document["clips"][3], "revision_id": "original", "in_frame": 6, "out_frame": 18}]
    result = compile_edit(source_list, document)
    assert result.shots[0].start_frame == 0
    assert result.shots[0].active.source_start_seconds == 3.25
    assert result.shots[0].active.media_range is None
    assert result.shots[0].frame_count == 12


def test_take_replacement_rejects_shorter_media(source_list):
    document = initial_document(source_list)
    document["clips"][0]["revision_id"] = "original"
    with pytest.raises(ManifestError, match="0..24"):
        compile_edit(source_list, document)


def test_occurrences_have_independent_takes_and_reject_nested_editors(source_list):
    document = initial_document(source_list)
    first = {**document["clips"][0], "in_frame": 0, "out_frame": 12}
    document["clips"] = [first, {**first, "id": "copy", "revision_id": "original"}]
    edited = compile_edit(source_list, document)
    assert edited.shots[0].active_revision_id == "take_001"
    assert edited.shots[1].active_revision_id == "original"
    assert source_list.shots[0].active_revision_id == "take_001"
    with pytest.raises(ManifestError, match="original shot list"):
        initial_document(edited)
    with pytest.raises(ManifestError, match="original shot list"):
        compile_edit(edited, document)


def test_invalid_json_and_placeholder_are_not_success_shaped(source_list):
    with pytest.raises(ManifestError, match="invalid JSON"):
        parse_document(source_list, "{")
    with pytest.raises(ManifestError):
        parse_document(source_list, "[]")
    placeholder = dataclasses.replace(source_list.source, template=True)
    shot = dataclasses.replace(source_list.shots[0], active_revision_id="original")
    with pytest.raises(ManifestError, match="generate a take"):
        initial_document(dataclasses.replace(source_list, source=placeholder, shots=(shot,)))


def test_render_decodes_correct_order_frames_audio_and_preserves_manifest(tmp_path):
    root = tmp_path / "projects"
    store = ProjectStore(root, "p_12345678")
    media = store.resolve("sources/source.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:s=128x128:r=24:d=4",
                    "-f", "lavfi", "-i", r"aevalsrc=sin(2*PI*if(lt(t\,2)\,440\,880)*t):s=48000:d=4",
                    "-vf", "drawbox=x=0:y=0:w=iw:h=ih:c=blue:t=fill:enable='gte(t,2)'",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(media)], check=True)
    src = Source("sources/source.mp4", "colors", 128, 128, 24, 1, "CFR", 96, 4, True)
    shots = tuple(Shot(f"S{i}", i, i * 48, (i + 1) * 48, None, None, 2, src.uri, "original",
                       (Revision("original", src.uri, 2, "original", media_range={"start_frame": i * 48}),))
                  for i in range(2))
    original = ShotList(store.dir.name, src, Detection("manual", .5, 1, "colors"), shots)
    store.write_json("manifest.json", original.to_dict())
    manifest = store.resolve("manifest.json").read_bytes()
    document = initial_document(original)
    document["clips"] = [document["clips"][1], document["clips"][0]]
    for clip in document["clips"]:
        clip.update(in_frame=12, out_frame=36)
    document["clips"].append({**document["clips"][0], "id": "blue_again"})
    edited = compile_edit(original, document)
    opts = AssemblyOptions(audio_policy="shot_audio", duration_policy="use_generated_duration")
    result = assemble_shots(edited, root, opts)
    assert probe(result.path).frame_count == 72
    assert result.duration_seconds == 3
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(result.path),
                                   "-vf", "fps=1,scale=1:1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    colors = np.frombuffer(raw, np.uint8).reshape(-1, 3)
    assert list(np.argmax(colors, axis=1)) == [2, 0, 2]
    audio = np.frombuffer(subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(result.path),
                                                  "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"]), dtype="<f4")
    for i, frequency in enumerate([880, 440, 880]):
        window = audio[i * 8000 + 1000:i * 8000 + 7000]
        measured = np.argmax(abs(np.fft.rfft(window))) * 8000 / len(window)
        assert abs(measured - frequency) < 5
    again = assemble_shots(ShotList.from_dict(edited.to_dict()), root, opts)
    assert again.reused and again.path == result.path
    fixed = assemble_shots(edited, root, dataclasses.replace(opts, fps_policy="fixed", output_fps=30))
    assert probe(fixed.path).frame_count == 90
    assert fixed.duration_seconds == 3
    assert store.resolve("manifest.json").read_bytes() == manifest
    tiny_document = initial_document(original)
    tiny_document["clips"] = [{**tiny_document["clips"][0], "id": f"tiny_{i}", "out_frame": 1} for i in range(3)]
    tiny = compile_edit(original, tiny_document)
    tiny_result = assemble_shots(tiny, root, dataclasses.replace(opts, fps_policy="fixed", output_fps=30, audio_policy="mute"))
    assert probe(tiny_result.path).frame_count == 4  # round(3 * 30/24), not 3 * round(30/24)
    with pytest.raises(AssemblyError, match="shorter than one output frame"):
        assemble_shots(tiny, root, dataclasses.replace(opts, fps_policy="fixed", output_fps=12))
    bad_shot = dataclasses.replace(edited.shots[0], active_revision_id="missing")
    with pytest.raises(ShotNotFoundError):
        assemble_shots(dataclasses.replace(edited, shots=(bad_shot,)), root, opts)
