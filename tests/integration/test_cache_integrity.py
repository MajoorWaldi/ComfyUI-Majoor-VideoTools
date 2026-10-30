import json
from pathlib import Path

from majoor_videotools.core.delivery_review import review_delivery, timeline_path
from majoor_videotools.core.export_transaction import atomic_json
from majoor_videotools.core.motion_score import read_score, write_score
from majoor_videotools.core.paths import ProjectStore


def test_missing_score_removes_previous_sidecar(tmp_path):
    store = ProjectStore(tmp_path, "p_12345678")
    video = store.resolve("exports/test.mp4")
    sidecar = Path(str(video) + ".score.json")
    sidecar.write_text("{}", encoding="utf-8")
    write_score(store, video, None)
    assert not sidecar.exists()


def test_corrupt_delivery_report_is_advisory_not_a_crash(tmp_path):
    video = tmp_path / "missing.mp4"
    timeline_path(video).write_text("{", encoding="utf-8")
    assert review_delivery(video)["reason"] == "invalid_assembly_timeline"


def test_unsupported_delivery_metadata_is_not_a_false_pass(tmp_path):
    video = tmp_path / "missing.mp4"
    timeline_path(video).write_text(json.dumps({"version": 999, "boundaries": []}), encoding="utf-8")
    assert review_delivery(video)["status"] == "not_evaluated"


def test_atomic_report_replacement_has_no_owned_temporary_left(tmp_path):
    report = tmp_path / "report.json"
    atomic_json(report, {"version": 1, "value": "old"})
    atomic_json(report, {"version": 2, "value": "new"})
    assert json.loads(report.read_text(encoding="utf-8")) == {"version": 2, "value": "new"}
    assert not list(tmp_path.glob("*.tmp"))


def test_invalid_score_json_is_treated_as_cache_miss(tmp_path):
    video = tmp_path / "missing.mp4"
    Path(str(video) + ".score.json").write_text("{", encoding="utf-8")
    assert read_score(video, [], 1, 24) is None
