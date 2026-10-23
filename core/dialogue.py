"""The dialogue of an edit, written as lines with their times ('0-3 s: "Welcome."', '00:10-00:13: Same man.'), cut down to what a shot says."""
import re

_TIME = r"(\d+:\d{2}(?:\.\d+)?|\d+(?:\.\d+)?)"
_LINE = re.compile(rf"^\s*{_TIME}\s*s?\s*[-–—]\s*{_TIME}\s*s?\s*[:\s]\s*(\S.*?)\s*$")
_SHOT = re.compile(r"(\d+:\d{2}(?:\.\d+)?)\s*[–-]\s*(\d+:\d{2}(?:\.\d+)?)")  # 00:11.466–00:12.333, the times of a shot in its header


def _seconds(text: str) -> float:
    minutes, _, seconds = text.rpartition(":")
    return (float(minutes) * 60 if minutes else 0.0) + float(seconds)


def lines_of_shot(shot_text: str, dialogue: str) -> str:
    """The lines that START inside the shot (the header of the shot gives its times), with their times counted from the start of the shot.
    Without the times of the shot, or when no line has times, the dialogue is kept as it is."""
    shot = _SHOT.search(shot_text)
    timed = [(m.group(1), m.group(2), m.group(3)) for m in map(_LINE.match, dialogue.splitlines()) if m]
    if not shot or not timed:
        return dialogue.strip()
    start, end = _seconds(shot.group(1)), _seconds(shot.group(2))
    return "\n".join(f"{_seconds(a) - start:.2f}-{min(_seconds(b), end) - start:.2f} s: {text}" for a, b, text in timed if start <= _seconds(a) < end)
