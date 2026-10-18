from comfy_api.latest import io

from ..adapters.comfy_video import MajoorShotList, MajoorShotMetadata, projects_root, video_file
from ..core.revisions import DURATION_POLICIES, apply_revision
from .preview import shots_payload


class MajoorApplyShotMetadata(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorApplyShotMetadata",
            display_name="Apply Shot Metadata",
            category="Majoor/VideoTools",
            has_intermediate_output=True,
            description="Attach a generated video to its shot as a new take. Returns an updated copy of the shot list.",
            inputs=[
                MajoorShotList.Input("shot_list"),
                MajoorShotMetadata.Input("metadata"),
                io.Video.Input("video"),
                io.String.Input("revision_label", default="", optional=True),
                io.Boolean.Input("activate_new_take", default=True),
                io.Combo.Input("duration_policy", options=list(DURATION_POLICIES), default="inherit_target", tooltip="inherit_target keeps the original shot duration; keep_generated lets Shot Assemble use the generated duration."),
            ],
            outputs=[MajoorShotList.Output(display_name="updated_shot_list")],
        )

    @classmethod
    def execute(cls, shot_list, metadata, video, activate_new_take, duration_policy, revision_label="") -> io.NodeOutput:
        with video_file(video) as path:
            updated = apply_revision(shot_list, projects_root(), metadata, path, revision_label, activate_new_take, duration_policy)
        shot = updated.get_shot(metadata.shot_id)
        return io.NodeOutput(updated, ui={"text": (f"{shot.shot_id} → {shot.active_revision_id} (revision {updated.project_revision})",), "majoor_shots": [shots_payload(updated)]})
