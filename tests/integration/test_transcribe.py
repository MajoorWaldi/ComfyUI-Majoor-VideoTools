"""Words and lyrics of a transcript: the rows the other nodes read, and the line the planners get."""
import json

from majoor_videotools.core.transcribe import lyrics_text, words_of
from majoor_videotools.core.words import parse_words

SEGMENTS = [
    {"text": "Frankenstein woke up", "start": 0.0, "end": 3.0, "words": [{"word": "Frankenstein", "start": 0.1, "end": 1.0}, {"word": "woke", "start": 1.2, "end": 1.5}, {"word": "up", "start": 1.6, "end": 2.0}]},
    {"text": "Dracula steps out", "start": 3.04, "end": 6.2, "words": [{"word": "Dracula", "start": 3.2, "end": 3.9}, {"word": "", "start": 4.0, "end": 4.1}, {"word": "steps", "start": 4.2, "end": 4.6}]},
]


def test_the_words_come_in_time_order_and_are_read_by_the_word_parser():
    words = words_of(SEGMENTS)
    assert [w["word"] for w in words] == ["Frankenstein", "woke", "up", "Dracula", "steps"]  # a blank word is left out
    assert [w["word"] for w in parse_words(json.dumps(words))] == [w["word"] for w in words]


def test_the_lyrics_are_one_line_per_phrase_with_their_seconds():
    assert lyrics_text(SEGMENTS) == "LYRICS (seconds):\n0.0-3.0 Frankenstein woke up\n3.0-6.2 Dracula steps out"
    assert lyrics_text([]) == "" and words_of([]) == []


def test_the_sections_come_as_a_line_for_the_planners():
    from majoor_videotools.core.music_structure import sections_text
    sections = [{"tag": "intro", "start": 0.0, "end": 6.4}, {"tag": "build", "start": 6.4, "end": 9.6}, {"tag": "drop", "start": 9.6, "end": 20.0}]
    assert sections_text(sections) == "SECTIONS OF THE MUSIC (seconds): intro 0.0-6.4, build 6.4-9.6, drop 9.6-20.0"
    assert sections_text([]) == ""


def test_a_voice_has_spoken_lines_not_lyrics():
    assert lyrics_text(SEGMENTS, spoken=True).startswith("SPOKEN LINES (seconds):" + chr(10) + "0.0-3.0 Frankenstein woke up")
