"""The JSON that the music_brief skills make (music_brief_from_plan, music_brief_yue2), read for a music model: ACE-Step, YuE2, MiniMax Music."""
import json
import math
import re

from .errors import MajoorError
from .template import _json_text

STEADY = "four on the floor, steady kick on every beat, constant tempo, no tempo change, clear transients"
SECONDS_PER_LINE = 6  # YuE2 sings a line in 4 to 6 s (measured: 12 lines 48 s, 16 lines 91 s)
_BPM = re.compile(r"\b\d{2,3}\s*BPM\b", re.IGNORECASE)
_TAG = re.compile(r"^\s*\[[^\]]+\]\s*$")


def fit_lyrics(lyrics: str, duration: float) -> str:
    """The lyrics cut to the lines that a song of `duration` seconds can use (one per 6 s, and one more), sections kept in order.

    A song model sings the lines in order and the length is capped elsewhere: the lines after the cap are never sung, they only make the song longer than the edit when the cap is lifted."""
    budget = max(2, math.ceil(duration / SECONDS_PER_LINE) + 1)
    sections: list[tuple[str, list[str]]] = []
    for line in lyrics.replace("\r\n", "\n").split("\n"):
        if _TAG.match(line):
            sections.append((line.strip(), []))
        elif line.strip():
            if not sections:
                sections.append(("", []))
            sections[-1][1].append(line.strip())
    kept = []
    for tag, lines in sections:
        lines = lines[:budget]
        budget -= len(lines)
        if lines or (tag and budget > 0):
            kept.append("\n".join([tag, *lines] if tag else lines))
        if budget <= 0:
            break
    return "\n\n".join(kept)


def read_brief(text: str, bpm: float = 0.0, duration: float = 0.0, steady: bool = True) -> tuple[str, int, float, str, str]:
    """Returns (music prompt or style, bpm, duration in seconds, sfx as JSON, lyrics fitted to the duration). A bpm or duration above 0 replaces the one of the brief."""
    try:
        data = json.loads(_json_text(text))
    except json.JSONDecodeError as e:
        raise MajoorError(f"The music brief is not JSON ({e.msg} at character {e.pos}). Use a music_brief skill.") from None
    style = str(data.get("music_prompt") or data.get("style") or "").strip() if isinstance(data, dict) else ""
    if not style:
        raise MajoorError("The music brief has no music_prompt (or style)")
    try:
        tempo = round(bpm if bpm > 0 else float(data["bpm"]))
        seconds = duration if duration > 0 else float(data["duration"])
    except (KeyError, TypeError, ValueError):
        raise MajoorError("The music brief needs a numeric bpm and duration (or set them on the node)") from None
    prompt = _BPM.sub(f"{tempo} BPM", style.rstrip(","))  # the tempo of the node replaces the one the LLM wrote in the style
    if steady:
        prompt += ", " + STEADY
    lyrics = fit_lyrics(str(data.get("lyrics") or ""), seconds) if str(data.get("lyrics") or "").strip() else ""
    return prompt, tempo, seconds, json.dumps(data.get("sfx") or []), lyrics
