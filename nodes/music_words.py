import json

from comfy_api.latest import io

from ..core.beats import detect_beats, read_wav_mono
from ..core.music_cuts import vocal_phrases
from ..core.music_structure import find_downbeats, track_sections
from ..core.sync_score import sync_score
from ..core.words import align_lyrics, mark_accents, parse_words
from .create_timeline import audio_file


class MajoorMusicWords(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorMusicWords",
            display_name="Music Words and Structure",
            category="Majoor/VideoTools",
            description="Read a music for the text and the cuts: the words with their times (given, or the lyrics spread over the vocal phrases), "
                        "the sections (intro, build, drop, break, outro) and the downbeats. No speech recognition: give words_json from a transcriber for exact times.",
            inputs=[
                io.Audio.Input("music"),
                io.String.Input("lyrics", multiline=True, default="", optional=True, tooltip="The words of the track, without times. They are spread over the vocal phrases of the music."),
                io.String.Input("words_json", default="", optional=True, force_input=True, tooltip="Words with times, [{word, start, end}] or {words: [...]}. Wins over lyrics."),
                io.Float.Input("accent_radius", default=0.12, min=0.0, max=1.0, step=0.01, optional=True, tooltip="A word is marked accent when a beat falls this close to its start."),
            ],
            outputs=[
                io.String.Output(display_name="words_json", tooltip="The words with their times; accent true on the words that land on a beat. Empty without lyrics or words."),
                io.String.Output(display_name="structure_json", tooltip="sections, drops, downbeats and, with words, the sync score of the words against the beats."),
                io.String.Output(display_name="phrases_text", tooltip="The vocal phrases as a line for an LLM: VOCAL PHRASES (seconds): 0.0-2.7, 3.6-5.8. Empty when the music has no voice."),
            ],
        )

    @classmethod
    def execute(cls, music, lyrics="", words_json="", accent_radius=0.12) -> io.NodeOutput:
        with audio_file(music) as wav:
            samples, rate = read_wav_mono(wav)
        _, beats = detect_beats(samples, rate)
        sections = track_sections(samples, rate)
        structure = {"sections": sections, "drops": [s["start"] for s in sections if s["tag"] == "drop"],
                     "downbeats": [round(t, 3) for t in find_downbeats(samples, rate, beats)]}
        phrases = vocal_phrases(samples, rate)
        structure["phrases"] = [[round(a, 2), round(b, 2)] for a, b in phrases]
        words = []
        if words_json.strip():
            words = parse_words(words_json)
        elif lyrics.strip():
            words = align_lyrics(lyrics, phrases or [(0.0, len(samples) / rate)])
        if words:
            words = mark_accents(words, [float(b) for b in beats], accent_radius)
            structure["sync"] = sync_score([w["start"] for w in words], [float(b) for b in beats])
        line = "VOCAL PHRASES (seconds): " + ", ".join(f"{a:.1f}-{b:.1f}" for a, b in phrases) if phrases else ""
        return io.NodeOutput(json.dumps(words) if words else "", json.dumps(structure), line, ui={"text": (f"{len(words)} words · " + ", ".join(f"{s['tag']} {s['start']:g}s" for s in sections),)})
