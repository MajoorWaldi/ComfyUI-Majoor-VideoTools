"""Immutable shot collection schema. The JSON form is the source of truth, not the Python classes."""
import dataclasses
from dataclasses import dataclass, field
from fractions import Fraction
import math
from pathlib import Path

from .errors import ManifestError, ShotNotFoundError

SCHEMA_VERSION = "1.0.0"
ORIGINAL = "original"


def _integer(value, name, *, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        bound = f" >= {minimum}" if minimum is not None else ""
        raise ManifestError(f"{name} must be an integer{bound}")


def _number(value, name, *, minimum=None, positive=False):
    try:
        finite = math.isfinite(value)
    except (TypeError, OverflowError):
        finite = False
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not finite:
        raise ManifestError(f"{name} must be a finite number")
    if (positive and value <= 0) or (minimum is not None and value < minimum):
        bound = "positive" if positive else f">= {minimum}"
        raise ManifestError(f"{name} must be {bound}")


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{name} must be non-empty text")


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
    # Runtime-only worker location; intentionally excluded from manifest JSON.
    storage_root: Path | None = field(default=None, compare=False, repr=False)

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
        if not isinstance(data, dict):
            raise ManifestError("Invalid manifest: expected an object")
        version = data.get("schema_version")
        if not isinstance(version, str) or version.split(".", 1)[0] != SCHEMA_VERSION.split(".", 1)[0]:
            raise ManifestError(f"Unsupported manifest schema_version '{version}'")
        try:
            if not isinstance(data.get("source"), dict) or not isinstance(data.get("detection"), dict):
                raise TypeError("source and detection must be objects")
            if not isinstance(data.get("shots"), list):
                raise TypeError("shots must be an array")
            detection = data["detection"]
            warnings = detection.get("warnings", ())
            beat_times = detection.get("beat_times", ())
            if not isinstance(warnings, (list, tuple)) or not isinstance(beat_times, (list, tuple)):
                raise TypeError("detection warnings and beat_times must be arrays")
            shots = tuple(
                Shot(**{**s, "revisions": tuple(Revision(**r) for r in s["revisions"])})
                for s in data["shots"]
            )
            result = cls(
                project_id=data["project_id"],
                source=Source(**data["source"]),
                detection=Detection(**{**detection, "warnings": tuple(warnings), "beat_times": tuple(beat_times)}),
                shots=shots,
                project_revision=data["project_revision"],
                schema_version=version,
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ManifestError(f"Invalid manifest: {e}") from e
        result.validate()
        return result

    def validate(self) -> None:
        _text(self.project_id, "project_id")
        _integer(self.project_revision, "project_revision", minimum=1)
        if not isinstance(self.schema_version, str) or self.schema_version.split(".", 1)[0] != SCHEMA_VERSION.split(".", 1)[0]:
            raise ManifestError(f"Unsupported manifest schema_version '{self.schema_version}'")
        if not isinstance(self.source, Source) or not isinstance(self.detection, Detection):
            raise ManifestError("Manifest source and detection must be valid records")
        source = self.source
        _text(source.uri, "source.uri")
        _text(source.fingerprint, "source.fingerprint")
        _text(source.timing_mode, "source.timing_mode")
        for name in ("width", "height", "fps_num", "fps_den", "frame_count", "time_base_num", "time_base_den"):
            _integer(getattr(source, name), f"source.{name}", minimum=1)
        _integer(source.rotation, "source.rotation")
        _integer(source.first_pts, "source.first_pts")
        _number(source.duration_seconds, "source.duration_seconds", positive=True)
        if type(source.has_audio) is not bool or type(source.template) is not bool:
            raise ManifestError("source.has_audio and source.template must be booleans")
        if source.audio_stream_index is not None:
            _integer(source.audio_stream_index, "source.audio_stream_index", minimum=0)
        if not isinstance(source.codec, str):
            raise ManifestError("source.codec must be text")

        detection = self.detection
        _text(detection.mode, "detection.mode")
        _text(detection.cache_key, "detection.cache_key")
        _number(detection.sensitivity, "detection.sensitivity", minimum=0)
        if detection.sensitivity > 1:
            raise ManifestError("detection.sensitivity must be between 0 and 1")
        _integer(detection.min_shot_frames, "detection.min_shot_frames", minimum=1)
        if not isinstance(detection.warnings, (tuple, list)) or any(not isinstance(item, str) for item in detection.warnings):
            raise ManifestError("detection.warnings must be an array of text")
        if not isinstance(detection.beat_times, (tuple, list)):
            raise ManifestError("detection.beat_times must be an array of times")
        for beat in detection.beat_times:
            _number(beat, "detection.beat_times[]", minimum=0)
        if detection.energy is not None and not isinstance(detection.energy, dict):
            raise ManifestError("detection.energy must be an object or null")

        if not isinstance(self.shots, (tuple, list)):
            raise ManifestError("shots must be an array")
        if any(not isinstance(shot, Shot) for shot in self.shots):
            raise ManifestError("shots must contain shot records")
        for shot in self.shots:
            _text(shot.shot_id, "shot_id")
            _integer(shot.timeline_index, f"{shot.shot_id}.timeline_index", minimum=0)
        ids = [s.shot_id for s in self.shots]
        if len(set(ids)) != len(ids):
            raise ManifestError("Duplicate shot ids in manifest")
        if not self.shots:
            raise ManifestError("Manifest contains no shots")
        expected_start = 0
        ordered = sorted(self.shots, key=lambda s: s.timeline_index)
        first_index = ordered[0].timeline_index
        if [shot.timeline_index for shot in ordered] != list(range(first_index, first_index + len(ordered))):
            raise ManifestError("Shot timeline indices must be unique and contiguous")
        for shot in ordered:
            _integer(shot.start_frame, f"{shot.shot_id}.start_frame", minimum=0)
            _integer(shot.end_frame_exclusive, f"{shot.shot_id}.end_frame_exclusive", minimum=1)
            if shot.start_frame != expected_start or shot.end_frame_exclusive <= shot.start_frame:
                raise ManifestError(f"{shot.shot_id}: invalid or overlapping frame range")
            expected_start = shot.end_frame_exclusive
            _number(shot.target_duration_seconds, f"{shot.shot_id}.target_duration_seconds", positive=True)
            _text(shot.source_media_ref, f"{shot.shot_id}.source_media_ref")
            if shot.source_media_ref != source.uri:
                raise ManifestError(f"{shot.shot_id}: source media reference differs from the project source")
            _text(shot.active_revision_id, f"{shot.shot_id}.active_revision_id")
            if shot.start_pts is not None:
                _integer(shot.start_pts, f"{shot.shot_id}.start_pts")
            if shot.end_pts_exclusive is not None:
                _integer(shot.end_pts_exclusive, f"{shot.shot_id}.end_pts_exclusive")
            if (shot.start_pts is None) != (shot.end_pts_exclusive is None):
                raise ManifestError(f"{shot.shot_id}: presentation timestamps must both be present or absent")
            if shot.start_pts is not None and shot.end_pts_exclusive <= shot.start_pts:
                raise ManifestError(f"{shot.shot_id}: invalid presentation timestamp range")
            if shot.thumbnail_ref is not None and not isinstance(shot.thumbnail_ref, str):
                raise ManifestError(f"{shot.shot_id}.thumbnail_ref must be text or null")
            if shot.plan is not None and not isinstance(shot.plan, dict):
                raise ManifestError(f"{shot.shot_id}.plan must be an object or null")
            if not isinstance(shot.revisions, (tuple, list)) or any(not isinstance(revision, Revision) for revision in shot.revisions):
                raise ManifestError(f"{shot.shot_id}.revisions must be an array of revision records")
            for revision in shot.revisions:
                _text(revision.revision_id, f"{shot.shot_id}.revision_id")
            rev_ids = [r.revision_id for r in shot.revisions]
            if len(set(rev_ids)) != len(rev_ids):
                raise ManifestError(f"{shot.shot_id}: duplicate revision ids")
            if ORIGINAL not in rev_ids or shot.active_revision_id not in rev_ids:
                raise ManifestError(f"{shot.shot_id}: missing original or active revision")
            original = next(revision for revision in shot.revisions if revision.revision_id == ORIGINAL)
            if original.status != "original" or original.media_ref != shot.source_media_ref or original.parent_revision_id is not None:
                raise ManifestError(f"{shot.shot_id}: original revision does not match the source media")
            revisions = {revision.revision_id: revision for revision in shot.revisions}
            revision_positions = {revision.revision_id: index for index, revision in enumerate(shot.revisions)}
            for position, revision in enumerate(shot.revisions):
                _text(revision.media_ref, f"{shot.shot_id}/{revision.revision_id}.media_ref")
                _number(revision.actual_duration_seconds, f"{shot.shot_id}/{revision.revision_id}.actual_duration_seconds", positive=True)
                _number(revision.source_start_seconds, f"{shot.shot_id}/{revision.revision_id}.source_start_seconds", minimum=0)
                _text(revision.status, f"{shot.shot_id}/{revision.revision_id}.status")
                for name in ("label", "fingerprint", "created_at", "generation_prompt"):
                    if not isinstance(getattr(revision, name), str):
                        raise ManifestError(f"{shot.shot_id}/{revision.revision_id}.{name} must be text")
                if type(revision.has_audio) is not bool:
                    raise ManifestError(f"{shot.shot_id}/{revision.revision_id}.has_audio must be a boolean")
                if not isinstance(revision.duration_policy, str) or revision.duration_policy not in ("inherit_target", "keep_generated"):
                    raise ManifestError(f"{shot.shot_id}/{revision.revision_id}: invalid duration policy")
                if revision.revision_id != ORIGINAL and revision.status != "generated":
                    raise ManifestError(f"{shot.shot_id}/{revision.revision_id}: non-original revision must be generated")
                if revision.parent_revision_id is not None:
                    _text(revision.parent_revision_id, f"{shot.shot_id}/{revision.revision_id}.parent_revision_id")
                    if revision.parent_revision_id not in revisions or revision.parent_revision_id == revision.revision_id:
                        raise ManifestError(f"{shot.shot_id}/{revision.revision_id}: inconsistent revision parent")
                    if revision_positions[revision.parent_revision_id] >= position:
                        raise ManifestError(f"{shot.shot_id}/{revision.revision_id}: revision parent must precede its child")
                if revision.media_range is not None:
                    if not isinstance(revision.media_range, dict) or not revision.media_range or set(revision.media_range) - {"start_frame", "end_frame_exclusive"}:
                        raise ManifestError(f"{shot.shot_id}/{revision.revision_id}: invalid media range")
                    start = revision.media_range.get("start_frame")
                    end = revision.media_range.get("end_frame_exclusive")
                    if start is not None:
                        _integer(start, f"{shot.shot_id}/{revision.revision_id}.media_range.start_frame", minimum=0)
                    if end is not None:
                        _integer(end, f"{shot.shot_id}/{revision.revision_id}.media_range.end_frame_exclusive", minimum=1)
                    if (start is not None and start >= source.frame_count) or (end is not None and end > source.frame_count) or (start is not None and end is not None and end <= start):
                        raise ManifestError(f"{shot.shot_id}/{revision.revision_id}: media range exceeds source bounds")
            for revision in shot.revisions:
                seen = set()
                current = revision
                while current.parent_revision_id is not None:
                    if current.revision_id in seen:
                        raise ManifestError(f"{shot.shot_id}: revision lineage contains a cycle")
                    seen.add(current.revision_id)
                    current = revisions[current.parent_revision_id]


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
    storage_root: Path | None = field(default=None, compare=False, repr=False)
