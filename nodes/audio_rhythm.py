import json

from comfy_api.latest import io

from ..core.audio_events import audio_rhythm_text
from ..core.beats import read_wav_mono
from ..core.timeline_sources import rhythm_text
from .create_timeline import audio_file


class MajoorAudioRhythm(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorAudioRhythm",
            display_name="Audio Rhythm",
            category="Majoor/VideoTools",
            description="Find the kicks, snares and hi-hats of a music and describe them shot by shot under the rhythm_text, "
                        "so that the LLM puts cuts on the kick and snare and only effects on the hi-hat. "
                        "Without music it gives the plain rhythm_text of the plan, and with an empty plan an empty text: it can stay in every graph.",
            inputs=[
                io.String.Input("plan_json", force_input=True, tooltip="The plan_json of Create Timeline or Cut Markers: its shots set the windows of the analysis. Empty: no rhythm."),
                io.Float.Input("fps", default=0.0, min=0.0, max=240.0, step=0.001, tooltip="0: the fps of the plan, or 24."),
                io.Float.Input("sensitivity", default=0.5, min=0.0, max=1.0, step=0.01, tooltip="Higher finds weaker hits."),
                io.Audio.Input("music", optional=True, tooltip="The music to analyse. Without it the rhythm_text has no audio lines."),
            ],
            outputs=[
                io.String.Output(display_name="rhythm_text"),
                io.String.Output(display_name="hits_json"),
            ],
        )

    @classmethod
    def execute(cls, plan_json, fps, sensitivity, music=None) -> io.NodeOutput:
        rate = fps if fps > 0 else 24.0
        if not plan_json.strip():
            return io.NodeOutput("", "{}")
        if music is None:
            text, hits = rhythm_text(plan_json, rate), {}
        else:
            with audio_file(music) as wav:
                samples, sample_rate = read_wav_mono(wav)
            text, hits = audio_rhythm_text(plan_json, rate, samples, sample_rate, sensitivity)
        return io.NodeOutput(text, json.dumps(hits), ui={"text": (text,)})
