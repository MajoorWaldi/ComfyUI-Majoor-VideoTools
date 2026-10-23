import contextlib

import comfy.model_management
import comfy.utils
from comfy_api.latest import VideoFromFile, io

from ..adapters.comfy_video import OUTPUT_SUBFOLDER, MajoorShotList, projects_root
from ..core.assembler import (
    AUDIO_POLICIES, CODECS, DURATION_POLICIES, FORMATS, FPS_POLICIES, MISSING_POLICIES, ORDER_MODES, AssemblyOptions, assemble_shots,
)
from ..core.timeline import format_timecode
from .create_timeline import audio_file


class MajoorShotAssemble(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorShotAssemble",
            display_name="Shot Assemble",
            category="Majoor/VideoTools",
            description="Rebuild a video from the active take of every shot. Untouched shots are kept as they are.",
            is_output_node=True,
            inputs=[
                MajoorShotList.Input("shot_list"),
                io.Combo.Input("assembly_mode", options=list(ORDER_MODES), default="original_order"),
                io.String.Input("manual_order", default="", multiline=True, optional=True, tooltip="manual_order: every shot id exactly once, comma separated or as a JSON array."),
                io.Combo.Input("missing_shot_policy", options=list(MISSING_POLICIES), default="error", tooltip="error stops on a missing take file or on a timeline-template shot that was never replaced. use_original falls back to the original shot (or keeps the placeholder card)."),
                io.Combo.Input("duration_policy", options=list(DURATION_POLICIES), default="trim_or_pad_last_frame"),
                io.Combo.Input("fps_policy", options=list(FPS_POLICIES), default="source"),
                io.Float.Input("output_fps", default=24.0, min=1.0, max=240.0, step=0.001, optional=True, tooltip="Used only when fps_policy is fixed."),
                io.Combo.Input("audio_policy", options=list(AUDIO_POLICIES), default="source_master"),
                io.Combo.Input("output_format", options=list(FORMATS), default="mp4"),
                io.Combo.Input("video_codec", options=list(CODECS), default="h264"),
                io.String.Input("output_name", default="majoor_edit"),
                io.Boolean.Input("effects", default=True, optional=True, tooltip="Apply the effects of the timeline plan (speed, zoom, flip, look, transitions, text). Off: plain shots."),
                io.Boolean.Input("sub_cuts", default=True, optional=True, tooltip="Cut every shot into the sub-cuts of the timeline plan. Off: one piece per shot."),
                io.Audio.Input("music", optional=True, tooltip="A music mixed over the audio chosen by audio_policy (mute: it is the only audio). Cut or padded with silence to the length of the edit."),
                io.Audio.Input("sfx", optional=True, tooltip="A sound-effects track, as long as the edit (for example the MMAudio / Foley output of the assembled edit), mixed with the music."),
                io.Float.Input("music_volume", default=1.0, min=0.0, max=4.0, step=0.05, optional=True),
                io.Float.Input("sfx_volume", default=1.0, min=0.0, max=4.0, step=0.05, optional=True),
                io.Float.Input("music_fade", default=0.5, min=0.0, max=10.0, step=0.1, optional=True, tooltip="Seconds of fade out at the end of the music."),
                io.Boolean.Input("replace_source_audio", default=False, optional=True, tooltip="Mute the soundtrack of the source: the music (and the sfx) are the only audio. Overrides audio_policy source_master; meant to be linked to a toggle."),
                io.Boolean.Input("voice_shots", default=False, optional=True, tooltip="Use the audio that each shot comes with (the voice that H3 speaks) as the audio of the edit. Overrides audio_policy; meant to be linked to a toggle."),
                io.Boolean.Input("text", default=True, optional=True, tooltip="Draw the text of the timeline plan with the other effects. Off: no text, the other effects stay. Meant to be linked to a toggle."),
            ],
            outputs=[io.Video.Output(display_name="video")],
        )

    @classmethod
    def execute(cls, shot_list, assembly_mode, missing_shot_policy, duration_policy, fps_policy, audio_policy, output_format, video_codec, output_name, manual_order="", output_fps=24.0, effects=True, sub_cuts=True, music=None, sfx=None, music_volume=1.0, sfx_volume=1.0, music_fade=0.5, replace_source_audio=False, voice_shots=False, text=True) -> io.NodeOutput:
        audio_policy = "shot_audio" if voice_shots else "mute" if replace_source_audio else audio_policy
        bar = comfy.utils.ProgressBar(1000)
        with contextlib.ExitStack() as stack:
            opts = AssemblyOptions(assembly_mode, manual_order, missing_shot_policy, duration_policy, fps_policy, output_fps, audio_policy, output_format, video_codec, output_name, effects, sub_cuts,
                                   stack.enter_context(audio_file(music)), stack.enter_context(audio_file(sfx)), music_volume, sfx_volume, music_fade, text)
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
