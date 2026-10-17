import dataclasses
import hashlib
from pathlib import Path

import pytest

from majoor_videotools.core.assembler import AssemblyOptions, assemble_shots
from majoor_videotools.core.errors import AssemblyError, ManifestError, MediaError, ShotNotFoundError
from majoor_videotools.core.frames import sample_original_shot
from majoor_videotools.core.media_probe import probe
from majoor_videotools.core.models import ShotList
from majoor_videotools.core.paths import ProjectStore
from majoor_videotools.core.revisions import apply_revision, find_revision, find_shot, make_metadata, revision_media
from majoor_videotools.core.scene_detection import detect_scenes


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def root(tmp_path):
    return tmp_path / "projects"


@pytest.fixture
def detected(fixtures, root):
    return detect_scenes(fixtures["hard"], root, "content", 0.5, 6)


def patch(shot_list, root, shot_id, video, **kw):
    shot = shot_list.get_shot(shot_id)
    meta = make_metadata(shot_list, shot, shot.active)
    return apply_revision(shot_list, root, meta, video, **kw)


def test_t01_single_shot(fixtures, root):
    sl = detect_scenes(fixtures["one"], root, "adaptive", 0.5, 6)
    assert [s.shot_id for s in sl.shots] == ["SHOT_001"]
    assert (sl.shots[0].start_frame, sl.shots[0].end_frame_exclusive) == (0, 72)


def test_t02_multiple_shots_contiguous(detected):
    assert [s.shot_id for s in detected.shots] == ["SHOT_001", "SHOT_002", "SHOT_003"]
    assert [(s.start_frame, s.end_frame_exclusive) for s in detected.shots] == [(0, 48), (48, 96), (96, 144)]
    detected.validate()


def test_manifest_json_roundtrip_and_cache(fixtures, root, detected):
    again = detect_scenes(fixtures["hard"], root, "content", 0.5, 6)
    assert again == detected
    assert ShotList.from_dict(detected.to_dict()) == detected
    store = ProjectStore(root, detected.project_id)
    assert store.resolve("manifest.json").exists()
    other = detect_scenes(fixtures["hard"], root, "content", 0.9, 6)
    assert other.project_id != detected.project_id  # new sensitivity = new collection identity


def test_manual_cuts(fixtures, root):
    sl = detect_scenes(fixtures["one"], root, "manual", 0.5, 6, cut_points="24, 00:00:02.0")
    assert [(s.start_frame, s.end_frame_exclusive) for s in sl.shots] == [(0, 24), (24, 48), (48, 72)]
    with pytest.raises(Exception, match="outside the video"):
        detect_scenes(fixtures["one"], root, "manual", 0.5, 6, cut_points="9999")


def test_short_shots_merged_with_warning(fixtures, root):
    sl = detect_scenes(fixtures["one"], root, "manual", 0.5, 6, cut_points="10, 12, 36")
    assert [(s.start_frame, s.end_frame_exclusive) for s in sl.shots][0][0] == 0
    assert all(s.frame_count >= 6 for s in sl.shots)
    assert sl.detection.warnings


def test_t03_t04_select(fixtures, root, detected):
    store = ProjectStore(root, detected.project_id)
    shot = find_shot(detected, "SHOT_002", 1)
    path = revision_media(store, detected, shot, find_revision(shot, "active", ""))
    info = probe(path)
    assert info.frame_count == 48 and abs(float(info.duration) - 2.0) < 0.05 and info.has_audio
    frames = sample_original_shot(store.resolve(detected.source.uri), detected.source, shot, "first_middle_last", 3, 128)
    assert frames.shape[0] == 3 and frames.shape[3] == 3 and max(frames.shape[1:3]) == 128
    with pytest.raises(ShotNotFoundError, match="Available shots"):
        find_shot(detected, "SHOT_099", 1)
    assert find_shot(detected, "", 3).shot_id == "SHOT_003"


def test_t05_t06_t07_t08_t09_apply(fixtures, root, detected):
    source_hash = sha(ProjectStore(root, detected.project_id).resolve(detected.source.uri))
    v2 = patch(detected, root, "SHOT_002", fixtures["gen"], label="draft")
    assert v2.get_shot("SHOT_002").active_revision_id == "take_001"
    assert v2.get_shot("SHOT_001") == detected.get_shot("SHOT_001")
    assert detected.get_shot("SHOT_002").active_revision_id == "original"  # upstream untouched

    again = patch(v2, root, "SHOT_002", fixtures["gen"])  # T09 idempotent
    assert again == v2
    again_from_v1 = patch(detected, root, "SHOT_002", fixtures["gen"])
    assert len(again_from_v1.get_shot("SHOT_002").revisions) == 2

    v3 = patch(v2, root, "SHOT_003", fixtures["gen_short"], activate=False)  # T07 / inactive take
    assert v3.get_shot("SHOT_003").active_revision_id == "original"
    assert len(v3.get_shot("SHOT_003").revisions) == 2
    take2 = patch(v2, root, "SHOT_002", fixtures["gen_short"])
    assert [r.revision_id for r in take2.get_shot("SHOT_002").revisions] == ["original", "take_001", "take_002"]

    # T08: feeding Select Shot's original clip back re-activates the original
    store = ProjectStore(root, detected.project_id)
    shot = take2.get_shot("SHOT_002")
    original_clip = revision_media(store, take2, shot, shot.revision("original"))
    restored = apply_revision(take2, root, make_metadata(take2, shot, shot.revision("original")), original_clip)
    assert restored.get_shot("SHOT_002").active_revision_id == "original"
    assert len(restored.get_shot("SHOT_002").revisions) == 3

    assert sha(store.resolve(detected.source.uri)) == source_hash  # T06


def test_apply_rejects_foreign_metadata(fixtures, root, detected):
    other = detect_scenes(fixtures["one"], root, "manual", 0.5, 6, cut_points="24")
    meta = make_metadata(other, other.get_shot("SHOT_001"), other.get_shot("SHOT_001").active)
    with pytest.raises(ManifestError, match="same Scene Detect"):
        apply_revision(detected, root, meta, fixtures["gen"])


def test_t10_roundtrip_original(fixtures, root, detected):
    res = assemble_shots(detected, root, AssemblyOptions())
    info = probe(res.path)
    assert info.frame_count == 144 and info.has_audio
    assert abs(float(info.duration) - 6.0) < 0.05
    assert not res.reused and res.modified_count == 0
    again = assemble_shots(detected, root, AssemblyOptions())
    assert again.reused and again.path == res.path


def test_t11_t12_replaced_shot_keeps_duration_and_audio(fixtures, root, detected):
    v2 = patch(detected, root, "SHOT_002", fixtures["gen"])  # 5 s of 30 fps media for a 2 s slot
    res = assemble_shots(v2, root, AssemblyOptions())
    info = probe(res.path)
    assert info.frame_count == 144 and abs(float(info.duration) - 6.0) < 0.05
    assert res.modified_count == 1 and any("SHOT_002" in w for w in res.warnings)
    assert info.has_audio


def test_pad_short_generated_media(fixtures, root, detected):
    v2 = patch(detected, root, "SHOT_002", fixtures["gen_short"])  # 1 s for a 2 s slot
    res = assemble_shots(v2, root, AssemblyOptions())
    assert probe(res.path).frame_count == 144
    with pytest.raises(AssemblyError, match="trim_or_error"):
        assemble_shots(v2, root, AssemblyOptions(duration_policy="trim_or_error"))


def test_retime_and_generated_duration(fixtures, root, detected):
    v2 = patch(detected, root, "SHOT_002", fixtures["gen"])
    retimed = assemble_shots(v2, root, AssemblyOptions(duration_policy="retime_to_target"))
    assert probe(retimed.path).frame_count == 144
    kept = assemble_shots(v2, root, AssemblyOptions(duration_policy="use_generated_duration"))
    assert abs(float(probe(kept.path).duration) - 9.0) < 0.1
    assert any("no longer in sync" in w for w in kept.warnings)


def test_keep_generated_directive(fixtures, root, detected):
    v2 = patch(detected, root, "SHOT_002", fixtures["gen"], duration_policy="keep_generated")
    res = assemble_shots(v2, root, AssemblyOptions())
    assert abs(float(probe(res.path).duration) - 9.0) < 0.1


def test_t13_manual_order(fixtures, root, detected):
    res = assemble_shots(detected, root, AssemblyOptions(assembly_mode="manual_order", manual_order="SHOT_003, SHOT_002, SHOT_001"))
    assert probe(res.path).frame_count == 144
    for bad, msg in (("SHOT_001,SHOT_001,SHOT_002", "more than once"), ("SHOT_001", "missing"), ("SHOT_001,SHOT_002,SHOT_009", "unknown")):
        with pytest.raises(AssemblyError, match=msg):
            assemble_shots(detected, root, AssemblyOptions(assembly_mode="manual_order", manual_order=bad))


def test_audio_policies_and_fixed_fps(fixtures, root, detected):
    mute = assemble_shots(detected, root, AssemblyOptions(audio_policy="mute"))
    assert not probe(mute.path).has_audio
    shot_audio = assemble_shots(detected, root, AssemblyOptions(audio_policy="shot_audio", fps_policy="fixed", output_fps=30.0))
    info = probe(shot_audio.path)
    assert info.has_audio and info.fps == 30 and info.frame_count == 180


def test_t16_missing_file(fixtures, root, detected):
    v2 = patch(detected, root, "SHOT_002", fixtures["gen"])
    store = ProjectStore(root, detected.project_id)
    store.resolve(v2.get_shot("SHOT_002").active.media_ref).unlink()
    with pytest.raises(MediaError, match="missing_shot_policy"):
        assemble_shots(v2, root, AssemblyOptions())
    res = assemble_shots(v2, root, AssemblyOptions(missing_shot_policy="use_original"))
    assert probe(res.path).frame_count == 144 and any("original shot used" in w for w in res.warnings)
    assert store.resolve("manifest.json").exists()


def test_corrupt_input(tmp_path, root):
    bad = tmp_path / "corrupt.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(MediaError, match="Cannot read media"):
        detect_scenes(bad, root, "manual", 0.5, 6, cut_points="1")


def test_project_paths_are_sandboxed(root, detected):
    store = ProjectStore(root, detected.project_id)
    with pytest.raises(Exception, match="escapes"):
        store.resolve("../../outside.txt")
    with pytest.raises(Exception, match="Invalid project id"):
        ProjectStore(root, "../evil")


def test_t18_concurrent_patches_keep_manifest_valid(fixtures, root, detected):
    from concurrent.futures import ThreadPoolExecutor

    jobs = [("SHOT_002", fixtures["gen"]), ("SHOT_003", fixtures["gen_short"])] * 3
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda j: patch(detected, root, *j), jobs))
    store = ProjectStore(root, detected.project_id)
    ShotList.from_dict(store.read_json("manifest.json"))
    assert not list((store.dir / "generated").glob("*.partial"))


def test_stray_timestamp_is_still_cfr_and_roundtrips(fixtures, root):
    sl = detect_scenes(fixtures["jitter"], root, "manual", 0.5, 6, cut_points="30, 60")
    assert sl.source.timing_mode == "CFR" and not sl.detection.warnings
    assert sl.source.frame_count == 90
    res = assemble_shots(sl, root, AssemblyOptions(audio_policy="mute"))
    assert probe(res.path).frame_count == 90
