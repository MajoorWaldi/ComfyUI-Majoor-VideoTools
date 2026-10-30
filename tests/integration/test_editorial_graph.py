import copy
import json
import subprocess
import sys
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from majoor_videotools.core.editorial_graph import compile_project, export_shot_list, preview_adapter
from majoor_videotools.core.errors import ManifestError
from majoor_videotools.core.models import ShotList
from majoor_videotools.core.timeline_edit import compile_edit, initial_document
from test_timeline_edit import source_list


def test_legacy_migration_is_deterministic_portable_and_non_destructive(source_list, tmp_path):
    before = source_list.to_dict()
    graph = compile_project(source_list)
    restored = ShotList.from_dict(json.loads(json.dumps(before)))
    assert compile_project(restored).to_dict() == graph.to_dict()
    assert compile_project(replace(restored, storage_root=tmp_path)).fingerprint == graph.fingerprint
    assert export_shot_list(graph, source_list) is source_list
    assert source_list.to_dict() == before
    assert str(tmp_path) not in json.dumps(graph.to_dict())
    assert all(clip["operation"] == "non_generative" for clip in graph.to_dict()["clips"])


def test_preview_and_export_consume_identical_rational_manual_windows(source_list):
    document = initial_document(source_list)
    first = {**document["clips"][3], "in_frame": 7, "out_frame": 31}
    document["clips"] = [first, {**first, "id": "copy", "in_frame": 31, "out_frame": 43}]
    graph = compile_project(source_list, document)
    preview = preview_adapter(graph)
    exported = export_shot_list(graph, source_list)
    assert exported == compile_edit(source_list, document)
    assert graph.duration == Fraction(3, 2)
    assert [clip["output_in_frame"] for clip in preview["clips"]] == [0, 24]
    assert [clip["output_out_frame"] for clip in preview["clips"]] == [24, 36]
    for window, shot in zip(graph.clips, exported.shots):
        assert float(window.source_start) == shot.active.source_start_seconds
        assert float(window.duration) == shot.target_duration_seconds
    assert len({clip.occurrence_id for clip in graph.clips}) == 2


def test_incremental_fingerprints_change_only_for_edited_occurrences(source_list):
    document = initial_document(source_list)
    before = compile_project(source_list, document)
    changed = copy.deepcopy(document)
    changed["clips"][2]["in_frame"] = 1
    after = compile_project(source_list, changed)
    # Later output positions necessarily change; previous occurrences remain reusable.
    assert [clip.fingerprint for clip in before.clips[:2]] == [clip.fingerprint for clip in after.clips[:2]]
    assert before.clips[2].fingerprint != after.clips[2].fingerprint
    assert before.fingerprint != after.fingerprint
    with pytest.raises(ManifestError, match="sources changed"):
        export_shot_list(before, replace(source_list, project_revision=2))


def test_fractional_timebase_never_accumulates_float_error(source_list):
    source = replace(source_list.source, fps_num=30000, fps_den=1001)
    sl = replace(source_list, source=source)
    document = initial_document(sl)
    first = {**document["clips"][0], "in_frame": 0, "out_frame": 1}
    document["clips"] = [{**first, "id": f"occurrence_{index}"} for index in range(1000)]
    graph = compile_project(sl, document)
    assert graph.duration == Fraction(1001, 30)
    assert preview_adapter(graph)["clips"][-1]["output_out_frame"] == 1000


def test_automatic_order_is_validated_and_changes_graph_identity(source_list):
    order = [shot.shot_id for shot in reversed(source_list.shots)]
    graph = compile_project(source_list, order=order)
    assert [clip.shot_id for clip in graph.clips] == order
    assert graph.fingerprint != compile_project(source_list).fingerprint
    with pytest.raises(ManifestError, match="every shot"):
        compile_project(source_list, order=order[:-1])


def test_procedural_benchmark_measures_real_frames_and_audio(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_editorial.py"
    subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path)], check=True,
                   capture_output=True, text=True, timeout=60)
    report = json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["frames"] == 144 and report["cut_error_frames"] == [0, 0, 0]
    assert report["measured_take_tones_hz"] == [880, 440, 660, 880]
    assert report["locked_music_tones_hz"] == [220] * 4
    assert report["release_approval"] is False
