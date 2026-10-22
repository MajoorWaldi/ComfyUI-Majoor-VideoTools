import hashlib
from pathlib import Path

import folder_paths
import numpy as np
from comfy_api.latest import io

from ..adapters.comfy_video import preview_ref, video_file
from ..core.beats import detect_beats, read_wav_mono, write_wav
from ..core.cut_markers import beat_grid, extend_beats, parse_markers, plan_from_markers, preview_mono, waveform_peaks
from ..core.errors import MajoorError
from ..core.media_probe import probe
from ..core.template import ASPECTS
from ..core.timeline_sources import plan_text, rhythm_text
from .create_timeline import audio_file


def _audio_preview(samples, rate) -> dict:
    """The music as a light wav under temp/, which the editor plays."""
    mono, light = preview_mono(samples, rate)
    key = hashlib.sha1(mono[:: max(len(mono) // 4096, 1)].tobytes() + str(len(mono)).encode()).hexdigest()[:16]
    folder = Path(folder_paths.get_temp_directory()) / "majoor_cuts"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{key}.wav"
    if not out.exists():
        write_wav(out, mono[:, None], light)
    return {"file": out.name, "folder": "majoor_cuts", "kind": "temp"}


class MajoorCutMarkers(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorCutMarkers",
            display_name="Cut Markers",
            category="Majoor/VideoTools",
            description="Place the cuts of an edit by hand on a timeline, over the waveform of a music, the cuts of a video and the beats. "
                        "Run once to load the media in the editor. Outputs the rhythm as a plan_json (the skeleton_json of Create Timeline) and a rhythm_text.",
            is_output_node=True,
            inputs=[
                io.Video.Input("video", optional=True, tooltip="A reference video: played in the editor, its cuts are shown and can be copied into markers."),
                io.Audio.Input("music", optional=True, tooltip="A music: its waveform and beats are shown in the editor."),
                io.String.Input("markers", multiline=True, default="", tooltip="Where the cuts are: seconds (12.5), timecodes (1:02.5) or frames (36f), separated by spaces. The editor writes them; you can type them too."),
                io.Float.Input("min_shot_seconds", default=1.0, min=0.2, max=30.0, step=0.1, tooltip="Each shot is generated once, so cuts in a row shorter than this are grouped into one shot; its cuts become its sub-cuts."),
                io.Float.Input("fps", default=0.0, min=0.0, max=240.0, step=0.001, tooltip="0: the video's fps, or 24."),
                io.Combo.Input("aspect_ratio", options=["auto", *ASPECTS], default="auto", tooltip="auto: left to Create Timeline."),
                io.Float.Input("duration", default=0.0, min=0.0, max=3600.0, step=0.01, tooltip="Seconds of the edit. 0: the video's, else the music's."),
                io.Float.Input("bpm", default=0.0, min=0.0, max=300.0, step=0.1, tooltip="0 detects the tempo of the music. With no music, a value draws a beat grid."),
                io.Int.Input("beats_per_bar", default=4, min=1, max=16),
                io.Int.Input("downbeat", default=0, min=0, max=15, tooltip="Beats between the first detected beat and the first beat of a bar."),
            ],
            outputs=[io.String.Output(display_name="plan_json"), io.String.Output(display_name="rhythm_text"), io.Int.Output(display_name="shot_count", tooltip="How many shots the markers make: connect it to max_shots of Deploy Shots.")],
        )

    @classmethod
    def execute(cls, markers, min_shot_seconds, fps, aspect_ratio, duration, bpm, beats_per_bar, downbeat, video=None, music=None) -> io.NodeOutput:
        payload: dict = {"video": None, "audio": None, "peaks": [], "beats": [], "bpm": 0.0, "beats_per_bar": beats_per_bar, "downbeat": downbeat, "video_cuts": []}
        length = 0.0
        rate = fps if fps > 0 else 24.0
        if video is not None:
            with video_file(video) as path:
                info = probe(path, with_packets=False)
                length = float(info.duration)
                if fps <= 0:
                    rate = float(info.fps)
                try:
                    from ..adapters import pyscenedetect

                    payload["video_cuts"] = [round(t, 4) for t in pyscenedetect.detect_cut_times(path, "adaptive", 0.5, max(round(0.1 * float(info.fps)), 1))]
                except ImportError:
                    pass  # no PySceneDetect: the editor simply has no cuts to copy
            payload["video"] = preview_ref(video)
        audio_length = 0.0
        with audio_file(music) as wav:
            if wav is not None:
                samples, sample_rate = read_wav_mono(wav)
                audio_length = len(samples) / sample_rate
                found, beats = detect_beats(samples, sample_rate, bpm)
                payload.update(peaks=waveform_peaks(samples), bpm=round(float(found), 2), audio=_audio_preview(samples, sample_rate))
        if audio_length == 0 and bpm > 0:
            payload["bpm"] = bpm
        total = duration if duration > 0 else (length or audio_length)
        times = parse_markers(markers, rate)
        if total <= 0:
            total = (times[-1] + 1.0) if times else 0.0
        if total <= 0:
            raise MajoorError("Connect a video or a music, or set duration, so the timeline has a length")
        if audio_length > 0:
            payload["beats"] = beat_grid(extend_beats(beats, float(found), total), total)
        elif bpm > 0:
            payload["beats"] = beat_grid(np.arange(0, total, 60.0 / bpm), total)
        plan, info = plan_from_markers(times, total, fps=rate, min_shot_seconds=min_shot_seconds, aspect_ratio=None if aspect_ratio == "auto" else aspect_ratio)
        text = plan_text(plan)
        payload.update(duration=round(total, 4), fps=rate, markers=times)
        summary = f"{len(times)} markers · {info['cuts']} cuts · {info['shots']} shots · {total:.2f} s" + "".join(f"\n⚠ {w}" for w in info["warnings"])
        return io.NodeOutput(text, rhythm_text(text, rate, f"{len(times)} markers"), info["shots"], ui={"text": (summary,), "majoor_cuts": [payload]})

