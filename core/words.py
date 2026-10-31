"""Word timing: the words of a track with their start and end seconds, from a transcript that already has times or from lyrics spread over the vocal phrases.

There is no speech recognition here. A word list is {"word", "start", "end"} rows in time order; lyrics without times are placed over the phrases
that `vocal_phrases` found, each word taking a share of its phrase as long as its letters, which is an estimate, not a forced alignment."""
import json
import math
import re

from .errors import MajoorError


def parse_words(text) -> list[dict]:
    """The rows of a JSON word list (a list, or an object with a "words" list), checked: finite, ordered, each word ending after it starts."""
    data = json.loads(text) if isinstance(text, str) else text
    rows = data.get("words") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        raise MajoorError("Words must be a non-empty list of {word, start, end}")
    words, last = [], 0.0
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("word"), str) or not row["word"].strip():
            raise MajoorError("Each word needs a non-empty text in 'word'")
        start, end = row.get("start"), row.get("end")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, end)) or start < 0 or end <= start:
            raise MajoorError(f"Word '{row['word']}' needs finite seconds with 0 <= start < end")
        if start < last - 1e-6:
            raise MajoorError(f"Word '{row['word']}' starts before the previous word")
        words.append({"word": row["word"].strip(), "start": float(start), "end": float(end)})
        last = float(start)
    return words


def align_lyrics(lyrics: str, phrases) -> list[dict]:
    """Spread the words of `lyrics` over `phrases` ((start, end) seconds), in order, each in proportion to its letters."""
    tokens = re.findall(r"\S+", lyrics)
    if not tokens or not phrases:
        raise MajoorError("Aligning lyrics needs words and at least one vocal phrase")
    weights = [max(len(re.sub(r"\W", "", t)), 1) + .5 for t in tokens]
    total, vocal = sum(weights), sum(b - a for a, b in phrases)

    def place(share, side):
        remaining = share / total * vocal
        for a, b in phrases:
            if remaining < b - a or (side == "end" and remaining <= b - a):
                return a + remaining
            remaining -= b - a
        return phrases[-1][1]

    words, done = [], 0.0
    for token, weight in zip(tokens, weights):
        words.append({"word": token, "start": round(place(done, "start"), 3), "end": round(place(done + weight, "end"), 3)})
        done += weight
    return words


def phrase_groups(words, max_gap=.35) -> list[tuple[float, float]]:
    """(start, end) of each run of words, split where the silence between two words is at least `max_gap` seconds."""
    groups = []
    for word in words:
        if groups and word["start"] - groups[-1][1] < max_gap:
            groups[-1] = (groups[-1][0], max(groups[-1][1], word["end"]))
        else:
            groups.append((word["start"], word["end"]))
    return groups


def mark_accents(words, accent_times, radius=.12) -> list[dict]:
    """The words, each with `accent` true when a strong musical accent falls within `radius` seconds of its start."""
    times = sorted(accent_times)
    return [{**w, "accent": any(abs(t - w["start"]) <= radius for t in times)} for w in words]


def word_offsets(words, layer_start: float) -> list[float]:
    """When each word appears, in seconds from the start of a text layer that shows them one after the other."""
    return [round(max(w["start"] - layer_start, 0.0), 3) for w in words]
