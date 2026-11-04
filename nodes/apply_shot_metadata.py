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
                io.String.Input("generation_prompt", default="", optional=True, force_input=True, tooltip="Exact prompt used for this take, retained separately from the editable shot plan."),
                io.Boolean.Input("activate_new_take", default=True),
                io.Combo.Input("duration_policy", options=list(DURATION_POLICIES), default="inherit_target", tooltip="inherit_target keeps the original shot duration; keep_generated lets Shot Assemble use the generated duration."),
                io.Boolean.Input("skip_copied_lead", default=False, optional=True, tooltip="A take generated with its source shot as reference video sometimes opens on a copy of it (the person it was asked to replace) "
                                 "before it cuts to what was asked. On: the take starts after that copy (its frames stay in the file). For a remix."),
                io.Boolean.Input("align_to_music", default=False, optional=True, tooltip="On: the take starts where its moments of strongest motion land best on the attacks of the music of the project "
                                 "(at most half a second in, and only when it lines up clearly more). Not for a shot cut inside, nor for one whose words are sung or spoken."),
            ],
            outputs=[MajoorShotList.Output(display_name="updated_shot_list")],
        )

    @classmethod
    def execute(cls, shot_list, metadata, video, activate_new_take, duration_policy, revision_label="", generation_prompt="", skip_copied_lead=False, align_to_music=False) -> io.NodeOutput:
        with video_file(video) as path:
            updated = apply_revision(shot_list, projects_root(shot_list), metadata, path, revision_label, activate_new_take, duration_policy, generation_prompt,
                                     skip_copied_lead, align_to_music)
        shot = updated.get_shot(metadata.shot_id)
        skipped = next((r.source_start_seconds for r in shot.revisions if r.revision_id == shot.active_revision_id), 0.0)
        note = f"; starts {skipped:.2f} s in" if skipped else ""
        return io.NodeOutput(updated, ui={"text": (f"{shot.shot_id} → {shot.active_revision_id} (revision {updated.project_revision}){note}",), "majoor_shots": [shots_payload(updated)]})
