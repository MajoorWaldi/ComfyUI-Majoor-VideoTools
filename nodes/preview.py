"""Data the frontend widgets (web/majoor_videotools.js) draw from. File entries avoid the
'filename'+'type' keys on purpose: ComfyUI registers any such entry in an executed output as an asset."""
from ..adapters.comfy_video import project_media_base
from ..core.fx import describe_shot
from ..core.models import ShotList
from ..core.timeline import shot_start


def shots_payload(shot_list: ShotList, clip: str | None = None, selected: str | None = None) -> dict:
    src = shot_list.source
    project_media_base(shot_list, src.uri)
    for shot in shot_list.shots:
        if shot.thumbnail_ref:
            project_media_base(shot_list, shot.thumbnail_ref)
        for revision in shot.revisions:
            project_media_base(shot_list, revision.media_ref)
    payload = {
        "base": project_media_base(shot_list),
        "revision": shot_list.project_revision,
        "source": {"file": src.uri, "fps": src.fps_num / src.fps_den, "duration": src.duration_seconds, "width": src.width, "height": src.height},
        "shots": [
            {
                "id": s.shot_id,
                "start": float(shot_start(src, s)),
                "duration": s.target_duration_seconds,
                "frames": s.frame_count,
                'generation_frames': (s.plan or {}).get('generation_frames',0),
                'render_source':(s.plan or {}).get('render_source',{}).get('kind','generated'),
                "thumb": s.thumbnail_ref,
                "active": s.active_revision_id,
                "takes": [r.revision_id for r in s.revisions],
                "prompt": (s.plan or {}).get("prompt", ""),
                "generation_prompt": s.active.generation_prompt,
                "rhythm": describe_shot(s.shot_id, float(shot_start(src, s)), s.target_duration_seconds, s.frame_count, s.plan, src.fps_num / src.fps_den)[1].split("\n", 1)[1],
            }
            for s in sorted(shot_list.shots, key=lambda s: s.timeline_index)
        ],
    }
    if clip is not None:
        payload["clip"] = clip
        payload["selected"] = selected
    return payload
