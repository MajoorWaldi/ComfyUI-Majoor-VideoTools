"""Immutable shot collection schema. The JSON form is the source of truth, not the Python classes."""
import dataclasses
from dataclasses import dataclass, field
from fractions import Fraction

from .errors import ManifestError, ShotNotFoundError

SCHEMA_VERSION = "1.0.0"
ORIGINAL = "original"


@dataclass(frozen=True)
class Source:
    uri: str
    fingerprint: str
    width: int
    height: int
    fps_num: int
    fps_den: int
    timing_mode: str
    frame_count: int
    duration_seconds: float
    has_audio: bool
    audio_stream_index: int | None = None
    time_base_num: int = 1
    time_base_den: int = 1
    rotation: int = 0
    first_pts: int = 0
    codec: str = ""
    template: bool = False  # the source is a generated placeholder video, not footage

    @property
    def fps(self) -> Fraction:
        return Fraction(self.fps_num, self.fps_den)

    @property
    def time_base(self) -> Fraction:
        return Fraction(self.time_base_num, self.time_base_den)


@dataclass(frozen=True)
class Revision:
    revision_id: str
    media_ref: str
    actual_duration_seconds: float
    status: str
    media_range: dict | None = None
    label: str = ""
    parent_revision_id: str | None = None
    fingerprint: str = ""
    duration_policy: str = "inherit_target"
    has_audio: bool = False
    created_at: str = ""
    source_start_seconds: float = 0.0  # non-destructive slip inside a generated take
    generation_prompt: str = ""


@dataclass(frozen=True)
class Shot:
    shot_id: str
    timeline_index: int
    start_frame: int
    end_frame_exclusive: int
    start_pts: int | None
    end_pts_exclusive: int | None
    target_duration_seconds: float
    source_media_ref: str
    active_revision_id: str
    revisions: tuple[Revision, ...]
    thumbnail_ref: str | None = None
    plan: dict | None = None  # prompt, image_prompt, notes and generation_frames of a timeline template

    def revision(self, revision_id: str) -> Revision:
        for rev in self.revisions:
            if rev.revision_id == revision_id:
                return rev
        raise ShotNotFoundError(
            f"{self.shot_id} has no revision '{revision_id}'. Available: {[r.revision_id for r in self.revisions]}"
        )

    @property
    def active(self) -> Revision:
        return self.revision(self.active_revision_id)

    @property
    def frame_count(self) -> int:
        return self.end_frame_exclusive - self.start_frame


@dataclass(frozen=True)
class Detection:
    mode: str
    sensitivity: float
    min_shot_frames: int
    cache_key: str
    warnings: tuple[str, ...] = ()
    beat_times: tuple[float, ...] = ()
    energy: dict | None = None


@dataclass(frozen=True)
class ShotList:
    project_id: str
    source: Source
    detection: Detection
    shots: tuple[Shot, ...]
    project_revision: int = 1
    schema_version: str = SCHEMA_VERSION

    def get_shot(self, shot_id: str) -> Shot:
        for shot in self.shots:
            if shot.shot_id == shot_id:
                return shot
        raise ShotNotFoundError(f"Unknown shot '{shot_id}'. Available shots: {[s.shot_id for s in self.shots]}")

    def with_shot(self, shot: Shot) -> "ShotList":
        shots = tuple(shot if s.shot_id == shot.shot_id else s for s in self.shots)
        return dataclasses.replace(self, shots=shots, project_revision=self.project_revision + 1)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "project_revision": self.project_revision,
            "source": dataclasses.asdict(self.source),
            "detection": {**dataclasses.asdict(self.detection), "warnings": list(self.detection.warnings)},
            "shots": [
                {**dataclasses.asdict(s), "revisions": [dataclasses.asdict(r) for r in s.revisions]}
                for s in self.shots
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ShotList":
        if data.get("schema_version", "").split(".")[0] != SCHEMA_VERSION.split(".")[0]:
            raise ManifestError(f"Unsupported manifest schema_version '{data.get('schema_version')}'")
        try:
            shots = tuple(
                Shot(**{**s, "revisions": tuple(Revision(**r) for r in s["revisions"])}) for s in data["shots"]
            )
            det = data["detection"]
            result = cls(
                project_id=data["project_id"],
                source=Source(**data["source"]),
                detection=Detection(**{**det, "warnings": tuple(det.get("warnings", ())), 'beat_times':tuple(det.get('beat_times',()))}),
                shots=shots,
                project_revision=data["project_revision"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError) as e:
            raise ManifestError(f"Invalid manifest: {e}") from e
        result.validate()
        return result

    def validate(self) -> None:
        ids = [s.shot_id for s in self.shots]
        if len(set(ids)) != len(ids):
            raise ManifestError("Duplicate shot ids in manifest")
        if not self.shots:
            raise ManifestError("Manifest contains no shots")
        expected_start = 0
        for shot in sorted(self.shots, key=lambda s: s.timeline_index):
            if shot.start_frame != expected_start or shot.end_frame_exclusive <= shot.start_frame:
                raise ManifestError(f"{shot.shot_id}: invalid or overlapping frame range")
            expected_start = shot.end_frame_exclusive
            rev_ids = [r.revision_id for r in shot.revisions]
            if len(set(rev_ids)) != len(rev_ids):
                raise ManifestError(f"{shot.shot_id}: duplicate revision ids")
            if ORIGINAL not in rev_ids or shot.active_revision_id not in rev_ids:
                raise ManifestError(f"{shot.shot_id}: missing original or active revision")


@dataclass(frozen=True)
class ShotMetadata:
    """Identity of a selected shot, passed from Select Shot to Apply Shot Metadata."""
    project_id: str
    shot_id: str
    timeline_index: int
    start_frame: int
    end_frame_exclusive: int
    target_duration_seconds: float
    source_fingerprint: str
    project_revision: int
    selected_revision_id: str
    revision_ids: tuple[str, ...] = field(default_factory=tuple)
