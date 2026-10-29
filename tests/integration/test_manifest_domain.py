import copy

import pytest

from majoor_videotools.core.errors import ManifestError
from majoor_videotools.core.models import Detection, ORIGINAL, Revision, Shot, ShotList, Source


def valid_manifest():
    source = Source("sources/source.mp4", "fixture", 64, 64, 24, 1, "CFR", 24, 1.0, False)
    original = Revision(
        ORIGINAL, source.uri, 1.0, "original",
        media_range={"start_frame": 0, "end_frame_exclusive": 24},
    )
    shot = Shot("SHOT_001", 1, 0, 24, 0, 24, 1.0, source.uri, ORIGINAL, (original,))
    return ShotList("p_12345678", source, Detection("manual", 0.5, 1, "fixture"), (shot,)).to_dict()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data["source"].update(fps_den=0),
        lambda data: data["source"].update(width=0),
        lambda data: data["source"].update(height=True),
        lambda data: data.update(project_revision=True),
        lambda data: data["shots"][0].update(timeline_index=True),
        lambda data: data["shots"][0].update(target_duration_seconds=-1),
        lambda data: data["shots"][0].update(target_duration_seconds=float("nan")),
        lambda data: data["shots"][0]["revisions"][0].update(actual_duration_seconds=float("inf")),
        lambda data: data["shots"][0].update(active_revision_id="missing"),
        lambda data: data["shots"][0]["revisions"][0].update(parent_revision_id="missing"),
        lambda data: data["shots"][0].update(source_media_ref="sources/other.mp4"),
    ],
)
def test_manifest_domain_validation_rejects_bad_snapshot_data(mutate):
    data = copy.deepcopy(valid_manifest())
    mutate(data)
    with pytest.raises(ManifestError):
        ShotList.from_dict(data)


def test_manifest_domain_validation_preserves_valid_roundtrip():
    data = valid_manifest()
    assert ShotList.from_dict(data).to_dict() == data
