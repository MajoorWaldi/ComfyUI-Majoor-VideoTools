import dataclasses

import pytest

from majoor_videotools.core.errors import ManifestError
from majoor_videotools.core.paths import ProjectStore
from majoor_videotools.core.scene_detection import detect_scenes, persist_manifest


def test_redetection_returns_persisted_collection_with_takes_and_notes(fixtures, tmp_path):
    original = detect_scenes(fixtures["one"], tmp_path, "manual", .5, 1, thumbnails=False)
    saved = original.with_shot(dataclasses.replace(original.shots[0], plan={"notes": "Keep this edit"}))
    store = ProjectStore(tmp_path, original.project_id)
    persist_manifest(store, saved)
    result = detect_scenes(fixtures["one"], tmp_path, "manual", .5, 1, thumbnails=False, force_refresh=True)
    assert result.to_dict() == saved.to_dict()
    assert result.storage_root == tmp_path.resolve()


def test_changed_detection_never_remaps_saved_shots(fixtures, tmp_path, monkeypatch):
    from majoor_videotools.core import scene_detection as detection

    original = detect_scenes(fixtures["one"], tmp_path, "manual", .5, 1, thumbnails=False)
    store = ProjectStore(tmp_path, original.project_id)
    before = store.resolve("manifest.json").read_bytes()
    monkeypatch.setattr(detection, "parse_cut_points", lambda *args: [24])
    with pytest.raises(ManifestError, match="boundaries changed"):
        detect_scenes(fixtures["one"], tmp_path, "manual", .5, 1, thumbnails=False, force_refresh=True)
    assert store.resolve("manifest.json").read_bytes() == before
