"""Assign complete timed lines to the shot where they start, without shortening a sentence at a picture cut."""
import re

_TIME = r"(\d+:\d{2}(?:\.\d+)?|\d+(?:\.\d+)?)"
_LINE = re.compile(rf"^\s*{_TIME}\s*s?\s*[-–—]\s*{_TIME}\s*s?\s*[:\s]\s*(\S.*?)\s*$")
_SHOT = re.compile(rf'{_TIME}\s*s?\s*[–-]\s*{_TIME}')


def _seconds(text: str) -> float:
    minutes, _, seconds = text.rpartition(":")
    return (float(minutes) * 60 if minutes else 0.0) + float(seconds)


def lines_of_shot(shot_text: str, dialogue: str, start: float | None = None, end: float | None = None) -> str:
    """The lines that START inside the shot (the header of the shot gives its times), with their times counted from the start of the shot.
    Without the times of the shot, or when no line has times, the dialogue is kept as it is."""
    shot = _SHOT.search(shot_text)
    timed = [(m.group(1), m.group(2), m.group(3)) for m in map(_LINE.match, dialogue.splitlines()) if m]
    if not timed:
        return dialogue.strip()
    if start is None or end is None:
        if not shot:
            return dialogue.strip()
        start, end = _seconds(shot.group(1)), _seconds(shot.group(2))
    return "\n".join(f"{_seconds(a) - start:.2f}-{_seconds(b) - start:.2f} s: {text}" for a, b, text in timed if start <= _seconds(a) < end)
