import comfy.model_management
import comfy.utils
from comfy_api.latest import VideoFromFile, io

from ..adapters.comfy_video import OUTPUT_SUBFOLDER, MajoorShotList, projects_root
from ..core.assembler import (
    AUDIO_POLICIES, CODECS, DURATION_POLICIES, FORMATS, FPS_POLICIES, MISSING_POLICIES, ORDER_MODES, AssemblyOptions, assemble_shots,
)
from ..core.timeline import format_timecode


class MajoorShotAssemble(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorShotAssemble",
            display_name="Majoor Shot Assemble",
            category="Majoor/VideoTools",
            description="Rebuild a video from the active take of every shot. Untouched shots are kept as they are.",
            is_output_node=True,
            inputs=[
                MajoorShotList.Input("shot_list"),
                io.Combo.Input("assembly_mode", options=list(ORDER_MODES), default="original_order"),
                io.String.Input("manual_order", default="", multiline=True, optional=True, tooltip="manual_order: every shot id exactly once, comma separated or as a JSON array."),
                io.Combo.Input("missing_shot_policy", options=list(MISSING_POLICIES), default="error"),
                io.Combo.Input("duration_policy", options=list(DURATION_POLICIES), default="trim_or_pad_last_frame"),
                io.Combo.Input("fps_policy", options=list(FPS_POLICIES), default="source"),
                io.Float.Input("output_fps", default=24.0, min=1.0, max=240.0, step=0.001, optional=True, tooltip="Used only when fps_policy is fixed."),
                io.Combo.Input("audio_policy", options=list(AUDIO_POLICIES), default="source_master"),
                io.Combo.Input("output_format", options=list(FORMATS), default="mp4"),
                io.Combo.Input("video_codec", options=list(CODECS), default="h264"),
                io.String.Input("output_name", default="majoor_edit"),
            ],
            outputs=[io.Video.Output(display_name="video")],
        )

    @classmethod
    def execute(cls, shot_list, assembly_mode, missing_shot_policy, duration_policy, fps_policy, audio_policy, output_format, video_codec, output_name, manual_order="", output_fps=24.0) -> io.NodeOutput:
        opts = AssemblyOptions(assembly_mode, manual_order, missing_shot_policy, duration_policy, fps_policy, output_fps, audio_policy, output_format, video_codec, output_name)
        bar = comfy.utils.ProgressBar(1000)
        result = assemble_shots(
            shot_list,
            projects_root(),
            opts,
            on_progress=lambda f: bar.update_absolute(int(f * 1000), 1000),
            is_cancelled=comfy.model_management.processing_interrupted,
        )
        summary = f"{result.shot_count} shots · {result.modified_count} modified · {format_timecode(result.duration_seconds)}" + ("\n(reused existing export)" if result.reused else "")
        summary += "".join(f"\n⚠ {w}" for w in result.warnings)
        preview = {"filename": result.path.name, "subfolder": f"{OUTPUT_SUBFOLDER}/{shot_list.project_id}/exports", "type": "output"}
        return io.NodeOutput(VideoFromFile(str(result.path)), ui={"images": [preview], "animated": (True,), "text": (summary,), "majoor_assembly": [{"shots": [{"id": i, "take": t, "duration": d} for i, t, d in result.timeline], "warnings": result.warnings}]})
