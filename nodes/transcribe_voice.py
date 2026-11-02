import json
import logging
import os
from pathlib import Path

import folder_paths
from comfy_api.latest import io

from ..core.beats import read_wav_mono
from ..core.errors import MajoorError
from ..core.music_cuts import vocal_phrases
from ..core.transcribe import lyrics_text, read_voice, words_of
from .create_timeline import audio_file

logger = logging.getLogger(__name__)
folder_paths.add_model_folder_path("faster-whisper", os.path.join(folder_paths.models_dir, "faster-whisper"))


def model_folder(name: str) -> Path:
    if not name or Path(name).name != name:
        raise MajoorError("The Whisper model is the name of a folder in models/faster-whisper")
    for root in folder_paths.get_folder_paths("faster-whisper"):
        if (Path(root) / name).is_dir():
            return Path(root) / name
    raise MajoorError(f"No Whisper model folder named {name} in models/faster-whisper: put the faster-whisper files of the model there (for example Systran/faster-whisper-large-v3)")


class MajoorTranscribeVoice(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorTranscribeVoice",
            display_name="Transcribe Voice",
            category="Majoor/VideoTools",
            description="Read the words sung or spoken in an audio with Whisper (faster-whisper, a model folder in models/faster-whisper, no download), with the time of each word. "
                        "words_json goes to Music Words and Create Timeline, lyrics_text to the prompt of the planners. A music without a voice gives nothing.",
            inputs=[
                io.Audio.Input("audio", optional=True, tooltip="Not connected: nothing is read."),
                io.String.Input("model", default="large-v3", tooltip="Name of the model folder in models/faster-whisper."),
                io.Combo.Input("device", options=["cpu", "cuda"], default="cpu", optional=True, tooltip="cuda is faster but shares the video memory with the other models."),
                io.String.Input("language", default="", optional=True, tooltip="Empty: Whisper finds the language. Or its code, en, fr..."),
                io.Boolean.Input("enabled", default=True, optional=True, tooltip="Off: nothing is read, whatever the audio."),
                io.Boolean.Input("spoken", default=False, optional=True, tooltip="The audio is a voice that speaks lines, not a song: lyrics_text says SPOKEN LINES instead of LYRICS."),
            ],
            outputs=[
                io.String.Output(display_name="words_json", tooltip="[{word, start, end}] in seconds. Empty without a voice."),
                io.String.Output(display_name="lyrics_text", tooltip="LYRICS (seconds): then one line per phrase, for an LLM. Empty without a voice."),
            ],
        )

    @classmethod
    def execute(cls, audio=None, model="large-v3", device="cpu", language="", enabled=True, spoken=False) -> io.NodeOutput:
        if audio is None or not enabled:
            return io.NodeOutput("", "", ui={"text": ("nothing to read",)})
        try:
            folder = model_folder(model)
            with audio_file(audio) as wav:
                samples, rate = read_wav_mono(wav)
                if not vocal_phrases(samples, rate):
                    return io.NodeOutput("", "", ui={"text": ("no voice found",)})
                segments = read_voice(wav, folder, device, language)
        except Exception as error:  # Whisper is an extra: whatever goes wrong with it (not installed, no model folder, a failure of its runtime), the job goes on without the words
            if type(error).__name__ == "InterruptProcessingException":
                raise
            logger.warning("Transcribe Voice: %s", error)
            return io.NodeOutput("", "", ui={"text": (f"not read: {error}",)})
        words = words_of(segments)
        return io.NodeOutput(json.dumps(words) if words else "", lyrics_text(segments, spoken), ui={"text": (f"{len(words)} words",)})
