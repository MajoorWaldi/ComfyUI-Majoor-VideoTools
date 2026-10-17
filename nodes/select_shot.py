import torch
from comfy_api.latest import io
from comfy_api.latest import VideoFromFile

from ..adapters.comfy_video import MajoorShotList, MajoorShotMetadata, projects_root
from ..core.frames import sample_original_shot, sample_whole_media
from ..core.media_probe import probe
from ..core.paths import ProjectStore
from ..core.revisions import TAKES, find_revision, find_shot, make_metadata, revision_media
from ..core.timeline import format_timecode, shot_start
from .preview import shots_payload

SAMPLING = ["first", "middle", "last", "first_middle_last", "uniform"]


class MajoorSelectShot(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorSelectShot",
            display_name="Majoor Select Shot",
            category="Majoor/VideoTools",
            description="Expose one shot (or one of its takes) as VIDEO, sample IMAGEs and identity metadata.",
            inputs=[
                MajoorShotList.Input("shot_list"),
                io.String.Input("shot_id", default="SHOT_001", tooltip="Stable shot id. When empty, index is used."),
                io.Int.Input("index", default=1, min=1, max=100000, optional=True, tooltip="1-based position, used only when shot_id is empty."),
                io.Combo.Input("take", options=list(TAKES), default="active", tooltip="active: the take used by Shot Assemble. revision_id: the take named below."),
                io.String.Input("revision_id", default="", optional=True),
                io.Combo.Input("frame_sampling", options=SAMPLING, default="first_middle_last"),
                io.Int.Input("sample_count", default=3, min=1, max=64, tooltip="Used by uniform sampling."),
                io.Int.Input("preview_resolution", default=768, min=64, max=4096, tooltip="Maximum size of the longest side of sampled images."),
            ],
            outputs=[
                io.Video.Output(display_name="video"),
                io.Image.Output(display_name="images"),
                MajoorShotMetadata.Output(display_name="metadata"),
            ],
        )

    @classmethod
    def execute(cls, shot_list, shot_id, take, frame_sampling, sample_count, preview_resolution, index=1, revision_id="") -> io.NodeOutput:
        shot = find_shot(shot_list, shot_id, index)
        revision = find_revision(shot, take, revision_id)
        store = ProjectStore(projects_root(), shot_list.project_id)
        path = revision_media(store, shot_list, shot, revision)

        if revision.media_range is not None:
            frames = sample_original_shot(store.resolve(shot_list.source.uri), shot_list.source, shot, frame_sampling, sample_count, preview_resolution)
        else:
            frames = sample_whole_media(path, probe(path, with_packets=False), frame_sampling, sample_count, preview_resolution)
        images = torch.from_numpy(frames).float() / 255.0

        start = float(shot_start(shot_list.source, shot))
        summary = (
            f"{shot.shot_id} · {revision.revision_id} ({revision.status}) · "
            f"{format_timecode(start)}–{format_timecode(start + shot.target_duration_seconds)} · {shot.target_duration_seconds:.2f}s"
        )
        return io.NodeOutput(VideoFromFile(str(path)), images, make_metadata(shot_list, shot, revision), ui={"text": (summary,), "majoor_shots": [shots_payload(shot_list, clip=store.rel(path), selected=shot.shot_id)]})
