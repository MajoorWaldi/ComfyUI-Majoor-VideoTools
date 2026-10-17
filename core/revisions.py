"""Select a shot / take, and apply a new take to a collection (copy-on-write)."""
import dataclasses
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .errors import ManifestError, MediaError, ShotNotFoundError
from .fingerprints import file_fingerprint, short
from .media_probe import probe
from .media_trim import clip_path, materialize_clip
from .models import ORIGINAL, Revision, Shot, ShotList, ShotMetadata
from .paths import ProjectStore
from .scene_detection import persist_manifest

TAKES = ("active", "original", "revision_id")
DURATION_POLICIES = ("inherit_target", "keep_generated")


def find_shot(shot_list: ShotList, shot_id: str, index: int) -> Shot:
    shot_id = shot_id.strip()
    if shot_id:
        return shot_list.get_shot(shot_id)
    for shot in shot_list.shots:
        if shot.timeline_index == index:
            return shot
    raise ShotNotFoundError(f"No shot at index {index}. The collection has {len(shot_list.shots)} shots.")


def find_revision(shot: Shot, take: str, revision_id: str) -> Revision:
    if take == "active":
        return shot.active
    if take == "original":
        return shot.revision(ORIGINAL)
    if not revision_id.strip():
        raise ShotNotFoundError("take='revision_id' requires a revision_id")
    return shot.revision(revision_id.strip())


def make_metadata(shot_list: ShotList, shot: Shot, revision: Revision) -> ShotMetadata:
    return ShotMetadata(
        project_id=shot_list.project_id,
        shot_id=shot.shot_id,
        timeline_index=shot.timeline_index,
        start_frame=shot.start_frame,
        end_frame_exclusive=shot.end_frame_exclusive,
        target_duration_seconds=shot.target_duration_seconds,
        source_fingerprint=shot_list.source.fingerprint,
        project_revision=shot_list.project_revision,
        selected_revision_id=revision.revision_id,
        revision_ids=tuple(r.revision_id for r in shot.revisions),
    )


def revision_clip_path(store: ProjectStore, shot_list: ShotList, shot: Shot, revision: Revision) -> Path:
    """Where the media handed out by Select Shot for this revision lives (no extraction)."""
    if revision.media_range is None:
        return store.resolve(revision.media_ref)
    return clip_path(store, shot_list.source, shot)


def revision_media(store: ProjectStore, shot_list: ShotList, shot: Shot, revision: Revision) -> Path:
    if revision.media_range is None:
        path = store.resolve(revision.media_ref)
        if not path.is_file():
            raise MediaError(f"{shot.shot_id}/{revision.revision_id}: media file is missing ({revision.media_ref})")
        return path
    if not store.resolve(shot_list.source.uri).is_file():
        raise MediaError(f"{shot.shot_id}: project source is missing ({shot_list.source.uri})")
    return materialize_clip(store, shot_list.source, shot)


def check_lineage(shot_list: ShotList, metadata: ShotMetadata) -> Shot:
    if metadata.project_id != shot_list.project_id:
        raise ManifestError(
            f"Shot metadata belongs to project {metadata.project_id} but the shot list is project {shot_list.project_id}. "
            "Connect the SHOT_METADATA and SHOT_LIST that come from the same Scene Detect node."
        )
    if metadata.source_fingerprint != shot_list.source.fingerprint:
        raise ManifestError("Shot metadata was produced from a different source video")
    shot = shot_list.get_shot(metadata.shot_id)
    if (shot.start_frame, shot.end_frame_exclusive) != (metadata.start_frame, metadata.end_frame_exclusive):
        raise ManifestError(f"{shot.shot_id}: the shot bounds changed since it was selected; refusing to patch")
    return shot


def apply_revision(
    shot_list: ShotList,
    store_root: Path,
    metadata: ShotMetadata,
    video_path: Path,
    label: str = "",
    activate: bool = True,
    duration_policy: str = "inherit_target",
) -> ShotList:
    shot = check_lineage(shot_list, metadata)
    store = ProjectStore(store_root, shot_list.project_id)
    video_path = Path(video_path).resolve()

    with store.lock():
        # Select Shot's own output fed straight back in re-activates that take instead of duplicating it.
        for rev in shot.revisions:
            if revision_clip_path(store, shot_list, shot, rev) == video_path:
                return _activated(store, shot_list, shot, rev.revision_id, activate)

        fingerprint = file_fingerprint(video_path)
        for rev in shot.revisions:
            if rev.fingerprint == fingerprint and rev.status == "generated":
                return _activated(store, shot_list, shot, rev.revision_id, activate)

        info = probe(video_path, with_packets=False)
        number = 1 + max((int(r.revision_id.split("_")[1]) for r in shot.revisions if r.revision_id.startswith("take_")), default=0)
        revision_id = f"take_{number:03d}"
        dest = store.resolve(f"generated/{shot.shot_id}_{revision_id}_{short(fingerprint)}{video_path.suffix.lower() or '.mp4'}")
        if not dest.exists():
            tmp = dest.with_name(dest.name + ".partial")
            shutil.copy2(video_path, tmp)
            tmp.replace(dest)
        revision = Revision(
            revision_id=revision_id,
            media_ref=store.rel(dest),
            actual_duration_seconds=float(info.duration),
            status="generated",
            media_range=None,
            label=label,
            parent_revision_id=metadata.selected_revision_id,
            fingerprint=fingerprint,
            duration_policy=duration_policy,
            has_audio=info.has_audio,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        patched = dataclasses.replace(
            shot,
            revisions=(*shot.revisions, revision),
            active_revision_id=revision_id if activate else shot.active_revision_id,
        )
        updated = shot_list.with_shot(patched)
        persist_manifest(store, updated)
        return updated


def _activated(store: ProjectStore, shot_list: ShotList, shot: Shot, revision_id: str, activate: bool) -> ShotList:
    if not activate or shot.active_revision_id == revision_id:
        return shot_list
    updated = shot_list.with_shot(dataclasses.replace(shot, active_revision_id=revision_id))
    persist_manifest(store, updated)
    return updated
