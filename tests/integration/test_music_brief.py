import json

import pytest

from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.music_brief import STEADY, fit_lyrics, read_brief

BRIEF = {"bpm": 127.6, "duration": 8.0, "music_prompt": "electronic, glossy, instrumental,", "sfx": [{"at": 0.75, "kind": "whip", "prompt": "whoosh"}]}
LYRICS = "[Verse]\nl1\nl2\nl3\nl4\n\n[Chorus]\nl5\nl6\nl7\nl8\n\n[Outro]\nl9\nl10"


def test_brief_in_a_fence_gives_tags_tempo_length_and_sfx():
    prompt, bpm, seconds, sfx, lyrics = read_brief("Here it is:\n```json\n" + json.dumps(BRIEF) + "\n```")
    assert prompt == "electronic, glossy, instrumental, " + STEADY and bpm == 128 and seconds == 8.0 and lyrics == ""
    assert json.loads(sfx)[0]["kind"] == "whip"


def test_node_values_replace_the_brief():
    prompt, bpm, seconds, _, _ = read_brief(json.dumps(BRIEF), bpm=120, duration=24, steady=False)
    assert prompt == "electronic, glossy, instrumental" and bpm == 120 and seconds == 24


def test_a_song_brief_gives_its_style_and_the_lyrics_that_fit_the_length():
    brief = {"bpm": 120, "duration": 8.0, "style": "English, male vocal, phonk", "lyrics": LYRICS}
    style, bpm, seconds, _, lyrics = read_brief(json.dumps(brief), steady=False)
    assert style == "English, male vocal, phonk" and bpm == 120
    assert lyrics == "[Verse]\nl1\nl2\nl3"  # 8 s: a line per 6 s and one more


def test_the_tempo_written_in_the_style_follows_the_node():
    brief = {"bpm": 140, "duration": 8.0, "style": "English, phonk, 140 BPM, 808"}
    assert read_brief(json.dumps(brief), steady=False)[0] == "English, phonk, 140 BPM, 808"
    assert read_brief(json.dumps(brief), bpm=128, steady=False)[0] == "English, phonk, 128 BPM, 808"


def test_lyrics_are_cut_by_lines_sections_stay_in_order_and_empty_ones_go():
    assert fit_lyrics(LYRICS, 8) == "[Verse]\nl1\nl2\nl3"
    assert fit_lyrics(LYRICS, 1) == "[Verse]\nl1\nl2"  # two lines at least
    assert fit_lyrics(LYRICS, 25) == "[Verse]\nl1\nl2\nl3\nl4\n\n[Chorus]\nl5\nl6"  # 6 lines
    assert fit_lyrics(LYRICS, 600) == LYRICS  # a long edit keeps everything
    assert fit_lyrics("no tags\nsecond line\nthird", 4) == "no tags\nsecond line"
    assert fit_lyrics("[Intro]\n\n[Verse]\nonly line", 8) == "[Intro]\n\n[Verse]\nonly line"
    assert fit_lyrics("", 8) == ""


@pytest.mark.parametrize("text", ["no json here", '{"bpm": 120}', '{"music_prompt": "x"}', '{"music_prompt": "x", "bpm": "fast", "duration": 5}', "[1, 2]"])
def test_unusable_briefs_are_refused(text):
    with pytest.raises(MajoorError):
        read_brief(text)
