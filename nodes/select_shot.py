import json

import torch
from comfy_api.latest import io
from comfy_api.latest import VideoFromFile

from ..adapters.comfy_video import MajoorShotList, MajoorShotMetadata, projects_root
from ..core.fx import describe_shot
from ..core.paths import ProjectStore
from ..core.revisions import TAKES, find_revision, find_shot, make_metadata, revision_media, sample_shot_images
from ..core.timeline import format_timecode, shot_start
from .preview import shots_payload

SAMPLING = ["first", "middle", "last", "first_middle_last", "uniform", "every_n"]


class MajoorSelectShot(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorSelectShot",
            display_name="Select Shot",
            category="Majoor/VideoTools",
            has_intermediate_output=True,
            description="Expose one shot (or one of its takes) as VIDEO, sample IMAGEs and identity metadata.",
            inputs=[
                MajoorShotList.Input("shot_list"),
                io.String.Input("shot_id", default="SHOT_001", tooltip="Stable shot id. When empty, index is used."),
                io.Int.Input("index", default=1, min=1, max=100000, optional=True, tooltip="1-based position, used only when shot_id is empty."),
                io.Combo.Input("take", options=list(TAKES), default="active", tooltip="active: the take used by Shot Assemble. revision_id: the take named below."),
                io.String.Input("revision_id", default="", optional=True),
                io.Combo.Input("frame_sampling", options=SAMPLING, default="first_middle_last"),
                io.Int.Input("sample_count", default=3, min=1, max=64, tooltip="uniform: how many frames, spread from the first to the last. every_n: at most this many frames."),
                io.Int.Input("preview_resolution", default=768, min=64, max=4096, tooltip="Maximum size of the longest side of sampled images."),
                io.Boolean.Input("start_from_previous", default=False, optional=True, tooltip="images becomes the last frame of the previous shot's active take, to continue from it. Generate shots one after the other."),
                io.Int.Input("every_n", default=8, min=1, max=100000, optional=True, tooltip="every_n sampling: frame 0, N, 2N... of the shot."),
                io.Boolean.Input("spread_to_end", default=True, optional=True, tooltip="every_n sampling: the last frame is always kept and, when more than sample_count would be kept, they are thinned evenly from the first to the last frame."),
            ],
            outputs=[
                io.Video.Output(display_name="video"),
                io.Image.Output(display_name="images"),
                MajoorShotMetadata.Output(display_name="metadata"),
                io.String.Output(display_name="prompt"),
                io.String.Output(display_name="image_prompt"),
                io.Int.Output(display_name="generation_frames"),
                io.Float.Output(display_name="generation_seconds"),
                io.String.Output(display_name="fx_json"),
                io.String.Output(display_name="rhythm_text"),
                io.String.Output(display_name="notes"),
                io.String.Output(display_name="location", tooltip="The place of the shot as the plan writes it (empty when the plan gives none): the text of its empty plate."),
                io.Float.Output(display_name="start_seconds", tooltip="Where the shot starts in the edit, in seconds."),
            ],
        )

    @classmethod
    def execute(cls, shot_list, shot_id, take, frame_sampling, sample_count, preview_resolution, index=1, revision_id="", start_from_previous=False, every_n=8, spread_to_end=True) -> io.NodeOutput:
        shot = find_shot(shot_list, shot_id, index)
        revision = find_revision(shot, take, revision_id)
        store = ProjectStore(projects_root(shot_list), shot_list.project_id)
        path = revision_media(store, shot_list, shot, revision)

        frames = sample_shot_images(store, shot_list, shot, revision, frame_sampling, sample_count, preview_resolution, start_from_previous, every_n, spread_to_end)
        images = torch.from_numpy(frames).float() / 255.0
        plan = shot.plan or {}
        # a quarter of a frame under the length to ask for: a generator that rounds a duration up to its frame grid (17k + 5) then lands on generation_frames, not one step above
        generation_seconds = (plan["generation_frames"] - 0.25) / float(shot_list.source.fps) if plan.get("generation_frames") else float(shot.target_duration_seconds)

        start = float(shot_start(shot_list.source, shot))
        fx_info, fx_text = describe_shot(shot.shot_id, start, float(shot.target_duration_seconds), shot.frame_count, plan, float(shot_list.source.fps))
        summary = (
            f"{shot.shot_id} · {revision.revision_id} ({revision.status}) · "
            f"{format_timecode(start)}–{format_timecode(start + shot.target_duration_seconds)} · {shot.target_duration_seconds:.2f}s"
        )
        return io.NodeOutput(VideoFromFile(str(path)), images, make_metadata(shot_list, shot, revision), plan.get("prompt", ""), plan.get("image_prompt", ""), plan.get("generation_frames", 0), generation_seconds, json.dumps(fx_info), fx_text, fx_info["notes"], plan.get("location", ""), start, ui={"text": (summary,), "majoor_shots": [shots_payload(shot_list, clip=store.rel(path), selected=shot.shot_id)]})
