"""Data the frontend widgets (web/majoor_videotools.js) draw from. File entries avoid the
'filename'+'type' keys on purpose: ComfyUI registers any such entry in an executed output as an asset."""
from ..adapters.comfy_video import OUTPUT_SUBFOLDER
from ..core.models import ShotList
from ..core.timeline import shot_start


def shots_payload(shot_list: ShotList, clip: str | None = None, selected: str | None = None) -> dict:
    src = shot_list.source
    payload = {
        "base": f"{OUTPUT_SUBFOLDER}/{shot_list.project_id}",
        "revision": shot_list.project_revision,
        "source": {"file": src.uri, "fps": src.fps_num / src.fps_den, "duration": src.duration_seconds, "width": src.width, "height": src.height},
        "shots": [
            {
                "id": s.shot_id,
                "start": float(shot_start(src, s)),
                "duration": s.target_duration_seconds,
                "frames": s.frame_count,
                "thumb": s.thumbnail_ref,
                "active": s.active_revision_id,
                "takes": [r.revision_id for r in s.revisions],
            }
            for s in sorted(shot_list.shots, key=lambda s: s.timeline_index)
        ],
    }
    if clip is not None:
        payload["clip"] = clip
        payload["selected"] = selected
    return payload
