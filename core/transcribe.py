"""The words of a sung or spoken track with their times, read by Whisper (faster-whisper) from a model folder on disk.

No download: the folder must already be there. A track with no voice gives no words, because Whisper invents some from music."""
from .errors import MajoorError

MAX_NO_SPEECH = .6  # a segment Whisper itself finds more likely to be silence than speech is dropped


def read_voice(path, model_dir, device: str = "cpu", language: str = "") -> list[dict]:
    """Segments {text, start, end, words: [{word, start, end}]} of the audio file, in time order. `language` empty: Whisper finds it."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise MajoorError("Transcribing needs faster-whisper: pip install faster-whisper") from None
    model = WhisperModel(str(model_dir), device=device, compute_type="auto", local_files_only=True)
    segments, _ = model.transcribe(str(path), language=language or None, word_timestamps=True, condition_on_previous_text=False)
    return [{"text": s.text.strip(), "start": round(s.start, 3), "end": round(s.end, 3),
             "words": [{"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)} for w in s.words]}
            for s in segments if s.no_speech_prob < MAX_NO_SPEECH and s.text.strip()]


def words_of(segments) -> list[dict]:
    """The words of all segments as {word, start, end} rows in time order: what `parse_words` reads."""
    return [word for segment in segments for word in segment["words"] if word["word"]]


def lyrics_text(segments, spoken: bool = False) -> str:
    """The words as lines for an LLM: LYRICS (seconds): then one line per phrase, 0.0-3.0 Frankenstein woke up; SPOKEN LINES (seconds) for a voice. Empty without segments."""
    if not segments:
        return ""
    return ("SPOKEN LINES" if spoken else "LYRICS") + " (seconds):\n" + "\n".join(f"{s['start']:.1f}-{s['end']:.1f} {s['text']}" for s in segments)
