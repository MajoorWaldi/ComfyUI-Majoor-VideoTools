import contextlib
import uuid

from comfy_api.latest import io

from ..adapters.comfy_video import MajoorShotList, projects_root, video_file
from ..core.beats import read_wav_mono, write_wav
from ..core.errors import MajoorError
from ..core.music_cuts import MODES, apply_music_timing, music_cut_plan
from ..core.prompt_guard import clean_plan_text
from ..core.template import ASPECTS, PROFILES, SNAP_MODES, create_template
from ..core.timeline import format_timecode
from ..core.timeline_sources import CUT_EVERY, VIDEO_MODES, ensure_burst, ensure_text, fit_duration, merge_plans, plan_from_music, plan_from_video, plan_text, rhythm_text, with_size
from .preview import shots_payload

DEFAULT_PLAN = '{"shots": [{"duration": 2.5, "prompt": ""}]}'


@contextlib.contextmanager
def audio_file(audio):
    """Write a ComfyUI AUDIO to a temporary wav, or yield None when there is no audio."""
    if audio is None:
        yield None
        return
    scratch = projects_root() / "_tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / f"{uuid.uuid4().hex}.wav"
    try:
        write_wav(path, audio["waveform"][0].detach().cpu().float().numpy().T, int(audio["sample_rate"]))
        yield path
    finally:
        path.unlink(missing_ok=True)


class MajoorCreateTimeline(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorCreateTimeline",
            display_name="Create Timeline",
            category="Majoor/VideoTools",
            description="Create a sequence of shots, without footage: from a JSON edit plan, cut on the bars and beats of a music, or on the cuts of a reference video. "
                        "Each shot is a plain color card to replace with a generated video, then reassemble.",
            is_output_node=True,
            inputs=[
                io.DynamicCombo.Input("source", options=[
                    io.DynamicCombo.Option("json", [
                        io.String.Input("plan_json", multiline=True, default=DEFAULT_PLAN,
                                        tooltip='{"fps", "aspect_ratio", "shots": [{"id", "duration" (seconds, "60f" or timecode), "prompt", "image_prompt", "notes", and optional effects rendered by Shot Assemble: "sub_cuts", "speed", "speed_ramp", "zoom", "focus", "flip", "look", "transition", "text"}]}. fps, aspect_ratio and resolution in the JSON override the widgets.'),
                        io.Combo.Input("cut_snap", options=list(SNAP_MODES), default="off", tooltip="With music: move each cut to the nearest half beat, beat or bar of four beats. Shots keep at least 5 frames; sub-cuts at least 3 and snap to half beats."),
                        io.Float.Input("bpm", default=0.0, min=0.0, max=300.0, step=0.1, tooltip="0 detects the tempo from the music."),
                        io.Float.Input("duration", default=0.0, min=0.0, max=3600.0, step=0.01, tooltip="Seconds of the edit: every shot of the plan is stretched or shrunk by the same factor so that they add up to it. 0 keeps the durations of the plan."),
                    ]),
                    io.DynamicCombo.Option("music", [
                        io.Combo.Input("cut_every", options=list(CUT_EVERY), default="bar", tooltip="Grid of the cuts, from the first beat of the music."),
                        io.Int.Input("shots", default=0, min=0, max=500, tooltip="0: one shot per grid step. Otherwise this many shots, with their cuts spread over the grid."),
                        io.Float.Input("duration", default=0.0, min=0.0, max=3600.0, step=0.01, tooltip="Seconds of the edit. 0 uses the whole music."),
                        io.Float.Input("bpm", default=0.0, min=0.0, max=300.0, step=0.1, tooltip="0 detects the tempo."),
                        io.Int.Input("beats_per_bar", default=4, min=1, max=16),
                        io.Int.Input("downbeat", default=0, min=0, max=15, tooltip="Beats between the first detected beat and the first beat of a bar (the tempo is detected, the bars are not)."),
                    ]),
                    io.DynamicCombo.Option("video", [
                        io.Combo.Input("detection_mode", options=list(VIDEO_MODES), default="adaptive"),
                        io.Float.Input("sensitivity", default=0.5, min=0.0, max=1.0, step=0.01, tooltip="Higher detects more cuts."),
                        io.Float.Input("min_cut_seconds", default=0.1, min=0.04, max=10.0, step=0.01, tooltip="Cuts closer than this are merged."),
                        io.Float.Input("min_shot_seconds", default=1.0, min=0.2, max=30.0, step=0.1,
                                       tooltip="Each shot is generated once, so short cuts in a row are grouped into one shot of at least this length; its original cuts become its sub-cuts."),
                        io.Combo.Input("cut_snap", options=list(SNAP_MODES), default="off", tooltip="With a music connected: move the cuts of the video to its half beats, beats or bars."),
                    ]),
                    io.DynamicCombo.Option("none", []),
                ], tooltip="json: a plan written by hand or by an LLM. music: shots cut on its bars or beats. video: shots with the rhythm of a reference video. none: no rhythm (empty plan_json and rhythm_text), to let the LLM decide."),
                io.Float.Input("fps", default=0.0, min=0.0, max=240.0, step=0.001, tooltip="0: automatic (the JSON's fps, the video's fps, or 24)."),
                io.Combo.Input("aspect_ratio", options=["auto", *ASPECTS], default="auto", tooltip="auto: the JSON's, the video's, or 16:9."),
                io.Int.Input("resolution", default=768, min=64, max=4096, tooltip="Longest side of the placeholder video."),
                io.Combo.Input("generation_profile", options=list(PROFILES), default="minimax_h3", tooltip="minimax_h3 asks generators for at least 124 frames, on the 17k+5 grid. generation_frames of Select Shot gives the number to request."),
                io.Audio.Input("music", optional=True, tooltip="Required by source=music. With json it is the master audio of the timeline (cut_snap uses it). Keep it with audio_policy=source_master in Shot Assemble."),
                io.Video.Input("video", optional=True, tooltip="Required by source=video."),
                io.Boolean.Input("preview_thumbnails", default=True, optional=True),
                io.Boolean.Input("card_text", default=True, optional=True, tooltip="Write the brief of each shot (id, place, role, transition, cuts, prompt) on its placeholder card, the text is wrapped and shrunk so that nothing is cut off. Off: plain colored cards."),
                io.Int.Input("width", default=0, min=0, max=4096, optional=True, tooltip="With height: the size in pixels of the placeholder video, instead of aspect_ratio and resolution. H3 generates at this size (multiples of 32 suit it). Connect Resolution Selector. 0: ignored."),
                io.Int.Input("height", default=0, min=0, max=4096, optional=True, tooltip="See width."),
                io.String.Input("skeleton_json", optional=True, force_input=True, tooltip="With source=json: the plan_json of another Create Timeline (music or video). Its shots, durations and the cuts inside them are kept; this plan only brings the prompts and the effects. Empty: ignored."),
                io.Boolean.Input('rhythm_reference_only', default=False, optional=True, tooltip='Expose musical timing as a guide rather than a fixed shot-count contract. Existing fixed skeletons remain unchanged.'),
                io.String.Input("project_root", default="", optional=True, force_input=True),
                io.Combo.Input("music_edit_mode", options=list(MODES), default="legacy", optional=True, tooltip="For source=json with music: adaptive energy-aware cuts, seeded random musical cuts, a regular grid, or free narrative timing. Legacy preserves existing workflows."),
                io.Combo.Input("music_cut_density", options=["auto", "low", "medium", "high"], default="auto", optional=True),
                io.Float.Input("music_cut_variation", default=0.5, min=0, max=1, step=0.01, optional=True),
                io.Float.Input("music_cut_sync", default=0.8, min=0, max=1, step=0.01, optional=True),
                io.Int.Input("music_cut_seed", default=42, min=0, max=0xffffffffffffffff, optional=True),
                io.Combo.Input("music_cut_every", options=list(CUT_EVERY), default="2_beats", optional=True),
                io.Combo.Input("music_cut_mood", options=["auto", "calm", "confident", "dreamy", "intense"], default="auto", optional=True, tooltip="Optional artistic mood bias. Acoustic energy and accents remain measured from the music."),
            ],
            outputs=[
                MajoorShotList.Output(display_name="shot_list"),
                io.String.Output(display_name="plan_json"),
                io.String.Output(display_name="rhythm_text"),
                io.Int.Output(display_name="shot_count", tooltip="How many shots: connect it to max_shots of Deploy Shots or to a loop."),
            ],
        )

    @classmethod
    def execute(cls, source, fps, aspect_ratio, resolution, generation_profile, music=None, video=None, preview_thumbnails=True, card_text=True, width=0, height=0, skeleton_json="", rhythm_reference_only=False,
                music_edit_mode="legacy", music_cut_density="auto", music_cut_variation=0.5, music_cut_sync=0.8,
                music_cut_seed=42, music_cut_every="2_beats", music_cut_mood="auto", project_root="") -> io.NodeOutput:
        kind = source["source"]
        rate = fps if fps > 0 else 24.0
        aspect = "16:9" if aspect_ratio == "auto" else aspect_ratio
        snap, bpm, extra = "off", 0.0, ""
        reference_beats, timing_warnings = (), ()
        with audio_file(music) as wav:
            notes: list[str] = []
            if kind == "none":
                shot_list = create_template(with_size(DEFAULT_PLAN, width, height) if width and height else DEFAULT_PLAN, projects_root(worker_root=project_root), fps=rate, aspect_ratio=aspect, resolution=resolution, profile=generation_profile, thumbnails=False)
                return io.NodeOutput(shot_list, "", "", len(shot_list.shots), ui={"text": ("No rhythm: the LLM decides.",), "majoor_shots": [shots_payload(shot_list)]})
            if kind == "json":
                text, snap, bpm = source["plan_json"], source["cut_snap"], source["bpm"]
                if source.get('duration',0.0) > 0 and not (skeleton_json or "").strip():
                    text = fit_duration(text, source['duration'], rate)
                if (skeleton_json or "").strip():
                    merged, notes = merge_plans(skeleton_json, text, rate, aspect, resolution)
                    text, extra = plan_text(merged), "rhythm from the skeleton"
                if music_edit_mode != "legacy":
                    if music_edit_mode not in MODES:
                        raise MajoorError(f"Unknown music edit mode: {music_edit_mode}")
                    if (skeleton_json or "").strip():
                        raise MajoorError("Choose either a fixed skeleton or a music editing mode, not both")
                    snap = "off"
                    if music_edit_mode != "free":
                        if wav is None:
                            raise MajoorError("Musical cut selection needs the music input")
                        samples, sample_rate = read_wav_mono(wav)
                        duration = source.get("duration", 0) or len(samples) / sample_rate
                        timing, info = music_cut_plan(samples, sample_rate, duration=duration, fps=rate,
                            mode=music_edit_mode, density=music_cut_density, variation=music_cut_variation,
                            sync=music_cut_sync, seed=music_cut_seed, cut_every=music_cut_every, mood=music_cut_mood)
                        merged, timing_notes = apply_music_timing(text, timing, rate, aspect, resolution)
                        text = plan_text(merged)
                        timing_warnings = tuple([*info["warnings"], *timing_notes])
                        beats = info["beat_times"]
                        reference_beats = tuple(sorted([*beats, *((a + b) / 2 for a, b in zip(beats, beats[1:]))]))
                        extra = f"{music_edit_mode} musical cut selection; generated takes preserved"
            elif kind == "music":
                if wav is None:
                    raise MajoorError("source=music needs the music input")
                samples, sample_rate = read_wav_mono(wav)
                plan, info = plan_from_music(samples, sample_rate, cut_every=source["cut_every"], duration=source["duration"], bpm=source["bpm"],
                                             beats_per_bar=source["beats_per_bar"], downbeat=source["downbeat"], shots=source["shots"], fps=rate)
                text, extra = plan_text(plan), (f"{info['bpm']} BPM, one cut every {source['cut_every']}" if info['bpm'] else 'No reliable pulse; narrative timing without a measured beat grid')
            elif kind == "video":
                if video is None:
                    raise MajoorError("source=video needs the video input")
                with video_file(video) as path:
                    plan, info = plan_from_video(path, detection_mode=source["detection_mode"], sensitivity=source["sensitivity"],
                                                 min_cut_seconds=source["min_cut_seconds"], min_shot_seconds=source["min_shot_seconds"], fps=fps)
                if aspect_ratio != "auto":
                    plan["aspect_ratio"] = aspect_ratio
                text, extra = plan_text(plan), f"{info['cuts']} cuts in the reference"
                rate, snap = plan["fps"], source["cut_snap"]
            else:
                raise MajoorError(f"Unknown source '{kind}'")
            if kind == "json":  # "one continuous take, no cuts, no text" contradicts the sub-cuts: the prompts of the plan never carry it
                text, dropped = clean_plan_text(text)
                if dropped:
                    notes.append(f"{len(dropped)} negation(s) removed from the prompts: {', '.join(sorted(set(dropped))[:4])}")
            if width and height:
                text = with_size(text, width, height)
            shot_list = create_template(text, projects_root(worker_root=project_root), fps=rate, aspect_ratio=aspect, resolution=resolution, profile=generation_profile,
                                        audio_wav=wav, cut_snap=snap, bpm=bpm, thumbnails=preview_thumbnails, card_text=card_text,
                                        reference_beats=reference_beats, timing_warnings=timing_warnings)
        src = shot_list.source
        summary = f"Timeline of {len(shot_list.shots)} shots Â· {format_timecode(src.duration_seconds)} Â· {src.fps_num / src.fps_den:.3f} fps Â· {src.width}x{src.height}"
        warnings = "".join(f"\nâš  {w}" for w in [*notes, *shot_list.detection.warnings])
        rhythm = rhythm_text(text, src.fps_num / src.fps_den, extra)
        if rhythm_reference_only:
            rhythm = 'MUSIC TIMING GUIDE (candidate grid cuts, not mandatory shot ids or a generated-take count):\n' + rhythm.replace('EDIT RHYTHM:', 'CANDIDATE GRID:', 1)
        return io.NodeOutput(shot_list, text, rhythm, len(shot_list.shots),
                             ui={"text": (summary + warnings,), "majoor_shots": [shots_payload(shot_list)]})


class MajoorEnsureBurst(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorEnsureBurst",
            display_name="Ensure Burst",
            category="Majoor/VideoTools",
            description="Add missing editorial accents on eligible takes for the requested density, preserving existing cuts and protected actions, without new generations. Optional approved words are added only when absent.",
            inputs=[io.String.Input("plan_json", multiline=True, force_input=True),
                    io.Combo.Input("density", options=["auto", "low", "medium", "high"], default="auto", tooltip="auto and low leave the plan as it is."),
                    io.Boolean.Input("enabled", default=True, tooltip="Off (the effects of the edit are off): the burst is not added."),
                    io.String.Input("text_allowed", default="", optional=True, tooltip="The words the user asked for: when the plan has no text, the last shot gets them."),
                    io.Boolean.Input("text_on", default=True, optional=True, tooltip="Off: no text is added.")],
            outputs=[io.String.Output(display_name="plan_json")],
        )

    @classmethod
    def execute(cls, plan_json, density, enabled, text_allowed="", text_on=True) -> io.NodeOutput:
        plan = ensure_burst(plan_json, density) if enabled else plan_json
        return io.NodeOutput(ensure_text(plan, text_allowed) if text_on else plan)
