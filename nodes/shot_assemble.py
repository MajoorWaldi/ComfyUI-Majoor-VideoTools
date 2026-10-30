import contextlib

import comfy.model_management
import comfy.utils
from comfy_api.latest import VideoFromFile, io

from ..adapters.comfy_video import project_media_base, MajoorShotList, projects_root
from ..core.assembler import (
    AUDIO_POLICIES, CODECS, DURATION_POLICIES, FORMATS, FPS_POLICIES, MISSING_POLICIES, ORDER_MODES, AssemblyOptions, assemble_shots,
)
from ..core.timeline import format_timecode
from ..core.beats import read_wav_mono
from ..core.errors import MajoorError
from ..core.music_cuts import MODES, musical_take_cuts
from ..core.dialogue_track import KEY as DIALOGUE_KEY
from ..core.timeline_sources import CUT_EVERY
from ..core.delivery_profiles import PROFILES, COLOR_POLICIES
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
                io.Combo.Input("audio_policy", options=list(AUDIO_POLICIES), default="source_master", tooltip="source_master: continuous original soundtrack, even after reorder. shot_audio: audio follows each selected take and trim (speed ramps are silent). mute: no take/source audio. Independent dialogue replaces these buses; supplied music remains locked at zero."),
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
                io.Float.Input("shot_volume", default=1.0, min=0.0, max=4.0, step=0.05, optional=True, tooltip="Volume of the sound that comes with each take (the sound design and the voice that H3 makes) when the audio is the one of the shots."),
                io.Float.Input("duck_music", default=0.0, min=0.0, max=1.0, step=0.05, optional=True, tooltip="How much the music gives way to the sound of the takes (a compressor on the music keyed by it). 0: not at all. Needs the audio of the shots and a music."),
                io.Boolean.Input("auto_sfx", default=False, optional=True, tooltip="Use the local Tone.js sound-design palette on actual cuts and transitions. User WAV cues override matching types; no extra model call. sfx_volume controls the mix."),
                io.String.Input("sfx_library",default="",optional=True,tooltip="Optional local WAV library folder with manifest.json recording file, license and source for each cue."),
                io.Float.Input("loudness_target", default=0.0, min=-40.0, max=0.0, step=0.5, optional=True, tooltip="Integrated loudness of the finished edit in LUFS, for example -14 for a social video; the true peak stays under -1.5 dBTP. 0 leaves the mix as it is."),
                io.String.Input('motion_layers',default='',optional=True,multiline=True,tooltip='Optional shared finishing layers. Explicit scene sfx cues follow the same local timings when auto_sfx is enabled.'),
                io.Combo.Input("music_edit_mode", options=list(MODES), default="legacy", optional=True, tooltip="Optional Remix excerpt cuts inside generated takes. Reference boundaries and raw takes remain unchanged."),
                io.Combo.Input("music_cut_density", options=["auto", "low", "medium", "high"], default="auto", optional=True),
                io.Float.Input("music_cut_variation", default=0.5, min=0, max=1, step=0.01, optional=True),
                io.Float.Input("music_cut_sync", default=0.8, min=0, max=1, step=0.01, optional=True),
                io.Int.Input("music_cut_seed", default=42, min=0, max=0xffffffffffffffff, optional=True),
                io.Combo.Input("music_cut_every", options=list(CUT_EVERY), default="2_beats", optional=True),
                io.Combo.Input("music_cut_mood", options=["auto", "calm", "confident", "dreamy", "intense"], default="auto", optional=True),
                io.Audio.Input("dialogue", optional=True, tooltip="Independent dialogue bus starting at zero. Replaces take audio, unaffected by video cuts/speed. Longer than the video is an error, never silently truncated."),
                io.Boolean.Input("preserve_dialogue", default=False, optional=True, tooltip="With voice_shots: preserve full available take audio on an independent bus. If a sentence/take exceeds the montage, stop and request an explicit dialogue edit rather than truncating it."),
                io.Combo.Input("delivery_profile", options=list(PROFILES), default="social", optional=True,
                               tooltip="Social keeps H.264. ProRes/DNxHR masters require MOV, preserve 10-bit processing and use PCM audio. ProRes 4444 retains alpha. Not an HDR/OCIO conversion."),
                io.Combo.Input("color_policy", options=list(COLOR_POLICIES), default="require_bt709", optional=True,
                               tooltip="Master profiles require tagged SDR BT.709 sources. assume_bt709 is an explicit assumption for untagged inputs, never a conversion from HDR."),
            ],
            outputs=[io.Video.Output(display_name="video")],
        )

    @classmethod
    def execute(cls, shot_list, assembly_mode, missing_shot_policy, duration_policy, fps_policy, audio_policy, output_format, video_codec, output_name, manual_order="", output_fps=24.0, effects=True, sub_cuts=True, music=None, sfx=None, music_volume=1.0, sfx_volume=1.0, music_fade=0.5, replace_source_audio=False, voice_shots=False, text=True, shot_volume=1.0, duck_music=0.0, auto_sfx=False,sfx_library="",motion_layers="",loudness_target=0.0,
                music_edit_mode="legacy", music_cut_density="auto", music_cut_variation=0.5, music_cut_sync=0.8,
                music_cut_seed=42, music_cut_every="2_beats", music_cut_mood="auto", dialogue=None, preserve_dialogue=False,
                delivery_profile="social", color_policy="require_bt709") -> io.NodeOutput:
        audio_policy = "shot_audio" if voice_shots else "mute" if replace_source_audio else audio_policy
        bar = comfy.utils.ProgressBar(1000)
        rhythm_warnings = []
        with contextlib.ExitStack() as stack:
            opts = AssemblyOptions(assembly_mode, manual_order, missing_shot_policy, duration_policy, fps_policy, output_fps, audio_policy, output_format, video_codec, output_name, effects, sub_cuts,
                                   stack.enter_context(audio_file(music)), stack.enter_context(audio_file(sfx)), music_volume, sfx_volume, music_fade, text, shot_volume, duck_music, auto_sfx,sfx_library,motion_layers,loudness_target)
            opts.dialogue = stack.enter_context(audio_file(dialogue))
            opts.delivery_profile = delivery_profile
            opts.color_policy = color_policy
            if preserve_dialogue and voice_shots and dialogue is None and not any(DIALOGUE_KEY in (s.plan or {}) for s in shot_list.shots):
                opts.preserve_dialogue = True
            if music_edit_mode not in MODES:
                raise MajoorError(f"Unknown music edit mode: {music_edit_mode}")
            if opts.preserve_dialogue and music_edit_mode not in ("legacy", "free"):
                rhythm_warnings.append("Musical recuts omitted to preserve spoken dialogue timing")
            elif music_edit_mode not in ("legacy", "free"):
                if opts.music is None:
                    raise MajoorError("Musical Remix cuts require the replacement music input")
                if assembly_mode != "original_order" or duration_policy != "trim_or_pad_last_frame":
                    raise MajoorError("Musical Remix cuts require original order and target shot durations")
                samples, rate = read_wav_mono(opts.music)
                shot_list = musical_take_cuts(shot_list, samples, rate, mode=music_edit_mode,
                    density=music_cut_density, variation=music_cut_variation, sync=music_cut_sync,
                    seed=music_cut_seed, cut_every=music_cut_every, mood=music_cut_mood)
                rhythm_warnings.extend(shot_list.detection.warnings)
            result = assemble_shots(
                shot_list,
                projects_root(shot_list),
                opts,
                on_progress=lambda f: bar.update_absolute(int(f * 1000), 1000),
                is_cancelled=comfy.model_management.processing_interrupted,
            )
            result.warnings.extend(rhythm_warnings)
        summary = f"{result.shot_count} shots · {result.modified_count} modified · {format_timecode(result.duration_seconds)}" + ("\n(reused existing export)" if result.reused else "")
        summary += "".join(f"\n⚠ {w}" for w in result.warnings)
        preview = {"filename": result.path.name, "subfolder": project_media_base(shot_list, "exports"), "type": "output"}
        return io.NodeOutput(VideoFromFile(str(result.path)), ui={"images": [preview], "animated": (True,), "text": (summary,), "majoor_assembly": [{"shots": [{"id": i, "take": t, "duration": d} for i, t, d in result.timeline], "warnings": result.warnings}]})
