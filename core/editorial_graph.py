"""Versioned, rational composition shared by legacy manifests and manual edits."""
import json
from dataclasses import dataclass, replace
from fractions import Fraction

from .errors import ManifestError
from .fingerprints import json_fingerprint
from .models import ShotList
from .timeline import shot_duration, shot_start

COMPILER_VERSION = "1"


def _rational(value: Fraction) -> list[int]:
    return [value.numerator, value.denominator]


@dataclass(frozen=True)
class ClipOccurrence:
    occurrence_id: str
    shot_id: str
    revision_id: str
    media_ref: str
    media_fingerprint: str
    source_start: Fraction
    duration: Fraction
    output_start: Fraction
    in_frame: int
    out_frame: int
    plan_json: str

    def to_dict(self):
        return {"id": self.occurrence_id, "shot_id": self.shot_id, "revision_id": self.revision_id,
                "media_ref": self.media_ref, "media_fingerprint": self.media_fingerprint,
                "source_start": _rational(self.source_start), "duration": _rational(self.duration),
                "output_start": _rational(self.output_start), "in_frame": self.in_frame, "out_frame": self.out_frame,
                "plan": json.loads(self.plan_json), "operation": "non_generative"}

    @property
    def fingerprint(self):
        return json_fingerprint(self.to_dict())


@dataclass(frozen=True)
class EditorialGraph:
    project_id: str
    project_revision: int
    source_signature: str
    fps: Fraction
    clips: tuple[ClipOccurrence, ...]
    document_json: str | None = None

    @property
    def duration(self):
        return sum((clip.duration for clip in self.clips), Fraction(0))

    def to_dict(self):
        document = json.loads(self.document_json) if self.document_json is not None else None
        return {"version": 1, "compiler": COMPILER_VERSION, "project_id": self.project_id,
                "project_revision": self.project_revision, "source_signature": self.source_signature,
                "fps": _rational(self.fps), "duration": _rational(self.duration),
                "clips": [clip.to_dict() for clip in self.clips],
                "dialogue": document.get("dialogue") if document is not None else None,
                "music_gain": document.get("music_gain", 1.) if document is not None else 1.,
                "manual": document is not None}

    @property
    def fingerprint(self):
        return json_fingerprint(self.to_dict())


def compile_project(shot_list: ShotList, document: dict | None = None, *, order=None) -> EditorialGraph:
    from .timeline_edit import source_signature, take_bounds, validate_document

    shot_list.validate()
    rows: list[dict]
    if document is not None:
        validate_document(shot_list, document)
        if order is not None:
            raise ManifestError("Editorial graph: manual document cannot have a second ordering")
        rows = document["clips"]
    else:
        ordered = sorted(shot_list.shots, key=lambda shot: shot.timeline_index)
        if order is not None:
            if len(order) != len(ordered) or set(order) != {shot.shot_id for shot in ordered}:
                raise ManifestError("Editorial graph: ordering must contain every shot exactly once")
            ordered = [shot_list.get_shot(shot_id) for shot_id in order]
        rows = [{"id": shot.shot_id, "shot_id": shot.shot_id, "revision_id": shot.active_revision_id}
                for shot in ordered]
    clips, cursor = [], Fraction(0)
    for row in rows:
        shot = shot_list.get_shot(row["shot_id"])
        revision = shot.revision(row["revision_id"])
        if document is not None:
            offset, _ = take_bounds(shot_list, shot, revision)
            begin, end = row["in_frame"], row["out_frame"]
            duration = Fraction(end - begin) / shot_list.source.fps
            start = offset + Fraction(begin) / shot_list.source.fps
            plan = {"prompt": (shot.plan or {}).get("prompt", "")}
        else:
            begin, end = 0, shot.frame_count
            duration = shot_duration(shot_list.source, shot)
            start = shot_start(shot_list.source, shot) if revision.media_range is not None else Fraction(str(revision.source_start_seconds))
            plan = shot.plan or {}
        try:
            plan_json = json.dumps(plan, sort_keys=True, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise ManifestError(f"{shot.shot_id}: editorial plan must contain finite JSON values") from error
        clips.append(ClipOccurrence(row["id"], shot.shot_id, revision.revision_id, revision.media_ref,
                                    revision.fingerprint, start, duration, cursor, begin, end, plan_json))
        cursor += duration
    return EditorialGraph(shot_list.project_id, shot_list.project_revision, source_signature(shot_list),
                          shot_list.source.fps, tuple(clips),
                          json.dumps(document, sort_keys=True, allow_nan=False) if document is not None else None)


def export_shot_list(graph: EditorialGraph, source: ShotList) -> ShotList:
    """Reversible legacy adapter: never write the generation manifest or raw takes."""
    from .timeline_edit import DIALOGUE_KEY, EDIT_KEY, MUSIC_GAIN_KEY, source_signature, take_bounds

    if (graph.project_id != source.project_id or graph.project_revision != source.project_revision
            or graph.source_signature != source_signature(source)):
        raise ManifestError("Editorial graph: sources changed; recompile before export")
    if graph.document_json is None:
        return source
    document = json.loads(graph.document_json)
    shots, cursor = [], 0
    for index, clip in enumerate(graph.clips):
        original = source.get_shot(clip.shot_id)
        revision = original.revision(clip.revision_id)
        length = clip.out_frame - clip.in_frame
        selected = replace(revision, media_range=None, source_start_seconds=float(clip.source_start),
                           duration_policy="inherit_target")
        revisions = tuple(selected if row.revision_id == selected.revision_id else row for row in original.revisions)
        plan = {**json.loads(clip.plan_json), EDIT_KEY: {
            "version": 1, "source_shot_id": clip.shot_id, "revision_id": clip.revision_id,
            "in_frame": clip.in_frame, "out_frame": clip.out_frame, "source_start_seconds": float(clip.source_start)}}
        shots.append(replace(original, shot_id=f"EDIT_{clip.occurrence_id}", timeline_index=index,
                             start_frame=cursor, end_frame_exclusive=cursor + length, start_pts=None,
                             end_pts_exclusive=None, target_duration_seconds=float(clip.duration),
                             active_revision_id=selected.revision_id, revisions=revisions, plan=plan))
        cursor += length
    if "dialogue" in document:
        entries = []
        for clip in document["dialogue"]:
            shot = source.get_shot(clip["shot_id"])
            revision = shot.revision(clip["revision_id"])
            offset, _ = take_bounds(source, shot, revision)
            entries.append({"file": revision.media_ref, "start": float(offset + Fraction(clip["in_frame"]) / graph.fps),
                            "duration": float(Fraction(clip["out_frame"] - clip["in_frame"]) / graph.fps),
                            "at": float(Fraction(clip["at_frame"]) / graph.fps), "gain": clip.get("gain", 1.)})
        shots[0] = replace(shots[0], plan={**shots[0].plan, DIALOGUE_KEY: entries})
    if "music_gain" in document:
        shots[0] = replace(shots[0], plan={**shots[0].plan, MUSIC_GAIN_KEY: document["music_gain"]})
    result = replace(source, shots=tuple(shots))
    result.validate()
    return result


def preview_adapter(graph: EditorialGraph) -> dict:
    """Raw-take windows; plan FX are declared, not falsely advertised as rendered."""
    return {"version": 1, "graph_fingerprint": graph.fingerprint, "fps_num": graph.fps.numerator,
            "fps_den": graph.fps.denominator, "duration": _rational(graph.duration),
            "rendering": "raw_takes_not_plan_fx", "clips": [
                {**clip.to_dict(), "fingerprint": clip.fingerprint,
                 "output_in_frame": round(clip.output_start * graph.fps),
                 "output_out_frame": round((clip.output_start + clip.duration) * graph.fps)}
                for clip in graph.clips]}
