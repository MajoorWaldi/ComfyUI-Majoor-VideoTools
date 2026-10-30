"""Frame-based, non-destructive edits compiled to an ordinary shot list."""
import json
import math
import re
from fractions import Fraction

from .errors import ManifestError
from .fingerprints import json_fingerprint
from .models import ShotList
from .timeline import shot_duration, shot_start

EDIT_KEY = "timeline_edit"
DIALOGUE_KEY = "dialogue_track"
MUSIC_GAIN_KEY = "timeline_music_gain"
MAX_CLIPS = 10000


def source_signature(shot_list: ShotList) -> str:
    return json_fingerprint([
        shot_list.project_id, shot_list.source.fingerprint,
        shot_list.source.fps_num, shot_list.source.fps_den,
        [[s.shot_id, s.start_frame, s.end_frame_exclusive, s.start_pts, s.end_pts_exclusive,
          [[r.revision_id, r.media_ref, r.fingerprint, r.actual_duration_seconds,
            r.media_range, r.source_start_seconds] for r in s.revisions]]
         for s in sorted(shot_list.shots, key=lambda s: s.timeline_index)],
    ])


def take_bounds(shot_list: ShotList, shot, revision) -> tuple[Fraction, int]:
    """Absolute file offset and available frames at the edit's timebase."""
    fps = shot_list.source.fps
    if revision.media_range is not None:
        if shot_list.source.template:
            raise ManifestError(f"{shot.shot_id}: generate a take before editing this placeholder")
        offset, duration = shot_start(shot_list.source, shot), shot_duration(shot_list.source, shot)
    else:
        if not math.isfinite(revision.source_start_seconds) or not math.isfinite(revision.actual_duration_seconds):
            raise ManifestError(f"{shot.shot_id}/{revision.revision_id}: non-finite take bounds")
        offset = Fraction(str(revision.source_start_seconds))
        duration = Fraction(str(revision.actual_duration_seconds)) - offset
    frames = int(duration * fps)
    if offset < 0 or frames < 1:
        raise ManifestError(f"{shot.shot_id}/{revision.revision_id}: invalid take bounds")
    return offset, frames


def initial_document(shot_list: ShotList) -> dict:
    if any(EDIT_KEY in (s.plan or {}) for s in shot_list.shots):
        raise ManifestError("Timeline Edit: connect the original shot list, not another Timeline Edit output")
    clips = []
    for i, shot in enumerate(sorted(shot_list.shots, key=lambda s: s.timeline_index)):
        _, frames = take_bounds(shot_list, shot, shot.active)
        length = frames if shot.active.duration_policy == "keep_generated" else min(frames, shot.frame_count)
        clips.append({"id": f"clip_{i + 1}", "shot_id": shot.shot_id, "revision_id": shot.active_revision_id,
                      "in_frame": 0, "out_frame": length})
    return {"version": 1, "project_id": shot_list.project_id, "source_signature": source_signature(shot_list),
            "fps_num": shot_list.source.fps_num, "fps_den": shot_list.source.fps_den, "clips": clips}


def dialogue_bounds(shot_list: ShotList, shot, revision) -> tuple[Fraction, int]:
    offset, frames = take_bounds(shot_list, shot, revision)
    if revision.media_range is not None:
        frames = int((Fraction(str(shot_list.source.duration_seconds)) - offset) * shot_list.source.fps)
        if frames < 1:
            raise ManifestError(f"{shot.shot_id}: no remaining source audio")
    return offset, frames


def validate_document(shot_list: ShotList, document: dict) -> None:
    if any(EDIT_KEY in (s.plan or {}) for s in shot_list.shots):
        raise ManifestError("Timeline Edit: connect the original shot list, not another Timeline Edit output")
    if not isinstance(document, dict) or type(document.get("version")) is not int or document["version"] != 1:
        raise ManifestError("Timeline Edit: unsupported document version")
    if document.get("project_id") != shot_list.project_id or document.get("source_signature") != source_signature(shot_list):
        raise ManifestError("Timeline Edit: sources or takes changed; reload the source list and explicitly start a new edit")
    if (any(type(document.get(k)) is not int for k in ("fps_num", "fps_den")) or
            (document["fps_num"], document["fps_den"]) != (shot_list.source.fps_num, shot_list.source.fps_den)):
        raise ManifestError("Timeline Edit: document frame rate differs from the source list")
    clips = document.get("clips")
    if not isinstance(clips, list) or not 1 <= len(clips) <= MAX_CLIPS:
        raise ManifestError(f"Timeline Edit: expected 1 to {MAX_CLIPS} clips")
    seen = set()
    for clip in clips:
        if not isinstance(clip, dict):
            raise ManifestError("Timeline Edit: each clip must be an object")
        cid = clip.get("id")
        if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", cid) or cid in seen:
            raise ManifestError("Timeline Edit: clip ids must be unique letters, digits, _ or - (1-80 characters)")
        seen.add(cid)
        if not isinstance(clip.get("shot_id"), str) or not isinstance(clip.get("revision_id"), str):
            raise ManifestError(f"{cid}: shot_id and revision_id must be strings")
        shot = shot_list.get_shot(clip["shot_id"])
        revision = shot.revision(clip["revision_id"])
        _, frames = take_bounds(shot_list, shot, revision)
        start, end = clip.get("in_frame"), clip.get("out_frame")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= frames:
            raise ManifestError(f"{cid}: in/out must be integer frames inside 0..{frames}, with out > in")
    if "dialogue" in document:
        dialogue = document["dialogue"]
        if not isinstance(dialogue, list) or len(dialogue) > 256:
            raise ManifestError("Timeline Edit: dialogue must contain at most 256 excerpts")
        seen = set()
        for clip in dialogue:
            if not isinstance(clip, dict):
                raise ManifestError("Timeline Edit: each dialogue excerpt must be an object")
            cid = clip.get("id")
            if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", cid) or cid in seen:
                raise ManifestError("Timeline Edit: dialogue ids must be unique")
            seen.add(cid)
            if not isinstance(clip.get("shot_id"), str) or not isinstance(clip.get("revision_id"), str):
                raise ManifestError("Timeline Edit: dialogue needs shot_id and revision_id")
            shot = shot_list.get_shot(clip["shot_id"])
            revision = shot.revision(clip["revision_id"])
            _, frames = dialogue_bounds(shot_list, shot, revision)
            start, end, at = (clip.get(k) for k in ("in_frame", "out_frame", "at_frame"))
            if any(type(n) is not int for n in (start, end, at)) or not 0 <= start < end <= frames or not 0 <= at <= 3600 * float(shot_list.source.fps):
                raise ManifestError("Timeline Edit: dialogue position and source window must be valid integer frames")
            gain = clip.get("gain", 1.)
            if type(gain) not in (int, float) or not math.isfinite(gain) or not 0 <= gain <= 1:
                raise ManifestError("Timeline Edit: dialogue gain must be between 0 and 1")
    if "music_gain" in document:
        gain = document["music_gain"]
        if type(gain) not in (int, float) or not math.isfinite(gain) or not 0 <= gain <= 1:
            raise ManifestError("Timeline Edit: music gain must be between 0 and 1")


def parse_document(shot_list: ShotList, text: str) -> dict:
    if not text.strip():
        return initial_document(shot_list)
    if len(text) > 4_000_000:
        raise ManifestError("Timeline Edit: document is too large")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Timeline Edit: invalid JSON: {exc}") from exc
    validate_document(shot_list, document)
    return document


def compile_edit(shot_list: ShotList, document: dict) -> ShotList:
    """Create independent occurrences; never persist over the generation manifest."""
    from .editorial_graph import compile_project, export_shot_list
    return export_shot_list(compile_project(shot_list, document), shot_list)
