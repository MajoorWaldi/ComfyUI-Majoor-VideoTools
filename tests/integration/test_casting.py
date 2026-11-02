import json
from types import SimpleNamespace

import pytest

from majoor_videotools.core.casting import bible_text, cast_shots, parse_casting
from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.skills import compose, load_skill, module_states


def _casting(**extra):
    data = {"style": "night, neon", "characters": [
        {"id": "ghoul", "name": "Ghoul", "look": "grey ghoul, black hood", "location": "rooftop", "performance": "rap", "start": 0, "end": 4},
        {"id": "witch", "name": "Witch", "look": "green witch, puffer", "start": 4, "end": 8}]}
    data.update(extra)
    return parse_casting("```json\n" + json.dumps(data) + "\n```")


def _shot(i, start, end):
    return SimpleNamespace(shot_id=f"SHOT_{i:03d}", start_frame=start, end_frame_exclusive=end)


def test_skill_loads():
    text, _ = compose(load_skill("casting_planner"), module_states(load_skill("casting_planner")))
    assert '"characters"' in text


def test_rejects_bad_casts():
    for bad in ('{"characters": []}', 'nope', '{"characters":[{"id":"a","name":"a","look":"x","start":1,"end":1}]}', '{"characters":[{"id":"a","name":"a","look":"x"}]}'):
        with pytest.raises(MajoorError):
            parse_casting(bad)
    # what an LLM writes loosely is understood: ids in capitals, a part written backwards, a size that does not exist
    loose = parse_casting('{"shot_sizes": ["Close Up", "huge"], "characters":[{"id":"Mad Witch","name":"Witch","look":"green","start":2,"end":1},{"id":"mad witch","name":"Twin","start":3,"end":4}]}')
    assert [c["id"] for c in loose["characters"]] == ["mad_witch", "mad_witch_2"] and (loose["characters"][0]["start"], loose["characters"][0]["end"]) == (1.0, 2.0)
    assert loose["shot_sizes"] == ["close_up"] and loose["characters"][1]["look"] == "Twin"


def test_bible_repeats_identity_and_style():
    text = bible_text(_casting(), "ghoul")
    assert "grey ghoul, black hood" in text and "night, neon" in text and "rooftop" in text
    with pytest.raises(MajoorError):
        bible_text(_casting(), "nobody")


def test_shots_follow_their_character_and_alternate_sizes():
    shots = [_shot(1, 0, 24), _shot(2, 24, 48), _shot(3, 48, 72), _shot(4, 96, 120), _shot(5, 120, 144)]
    cast = cast_shots(_casting(), shots, 24)
    assert [cast[f"SHOT_{i:03d}"]["character_id"] for i in range(1, 6)] == ["ghoul", "ghoul", "ghoul", "witch", "witch"]
    assert [cast[f"SHOT_{i:03d}"]["shot_size"] for i in range(1, 6)] == ["medium", "close_up", "medium", "medium", "close_up"]
    assert cast["SHOT_001"]["location"] == "rooftop" and cast["SHOT_001"]["performance"] == "rap"


def test_apply_casting_writes_identity_into_plans_and_is_repeatable():
    from dataclasses import dataclass, replace

    @dataclass(frozen=True)
    class Shot:
        shot_id: str
        start_frame: int
        end_frame_exclusive: int
        plan: dict | None = None

    @dataclass(frozen=True)
    class ShotList:
        source: SimpleNamespace
        shots: tuple

    from majoor_videotools.core.casting import apply_casting
    shot_list = ShotList(SimpleNamespace(fps=24), (Shot("SHOT_001", 0, 48, {"prompt": "he raps"}), Shot("SHOT_002", 120, 168)))
    once = apply_casting(shot_list, _casting())
    twice = apply_casting(once, _casting())
    assert twice == once
    plan = once.shots[0].plan
    assert plan["prompt"].endswith("he raps") and "grey ghoul" in plan["prompt"] and "Shot size: medium." in plan["prompt"]
    assert plan["location"] == "rooftop" and plan["cast"]["base_prompt"] == "he raps"
    assert once.shots[1].plan["cast"]["character_id"] == "witch" and "location" not in once.shots[1].plan


def test_references_energy_and_auto_sizes_reach_every_plan():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Shot:
        shot_id: str
        start_frame: int
        end_frame_exclusive: int
        plan: dict | None = None

    @dataclass(frozen=True)
    class ShotList:
        source: SimpleNamespace
        shots: tuple

    from majoor_videotools.core.casting import apply_casting, parse_references
    casting = _casting(shot_sizes="auto")
    shots = tuple(Shot(f"SHOT_{i:03d}", a, b, {"prompt": f"p{i}"}) for i, (a, b) in enumerate([(0, 72), (72, 90), (90, 100), (100, 190), (190, 192)], 1))
    references = parse_references('{"ghoul": ["g1.png", "g2.png"]}', casting)
    done = apply_casting(ShotList(SimpleNamespace(fps=24), shots), casting, references, {"SHOT_003": .9})
    sizes = [s.plan["cast"]["shot_size"] for s in done.shots]
    assert sizes[0] == "wide"                                                     # the opening shot is long enough to establish the place
    assert done.shots[2].plan["cast"]["shot_size"] in ("close_up", "extreme_close_up")  # 0.42 s and energetic
    assert done.shots[0].plan["cast"]["references"] == ["g1.png", "g2.png"]       # every shot of the ghoul carries its pictures
    assert all("references" not in s.plan["cast"] for s in done.shots if s.plan["cast"]["character_id"] == "witch")
    assert apply_casting(done, casting, references, {"SHOT_003": .9}) == done      # still repeatable


def test_each_shot_gets_the_words_sung_in_it_and_applying_them_again_replaces_them():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Shot:
        shot_id: str
        start_frame: int
        end_frame_exclusive: int
        plan: dict | None = None

    @dataclass(frozen=True)
    class ShotList:
        source: SimpleNamespace
        shots: tuple

    from majoor_videotools.core.casting import apply_casting, apply_lyrics
    words = [{"word": "Frankenstein", "start": .1, "end": 1.0}, {"word": "woke", "start": 1.2, "end": 1.5}, {"word": "Dracula", "start": 2.5, "end": 3.0}]
    shots = (Shot("SHOT_001", 0, 48, {"prompt": "he raps"}), Shot("SHOT_002", 48, 120, {"prompt": "she raps"}), Shot("SHOT_003", 120, 144, {"prompt": "silence"}))
    done = apply_lyrics(ShotList(SimpleNamespace(fps=24), shots), words)
    assert 'word for word: "Frankenstein woke"' in done.shots[0].plan["prompt"] and done.shots[0].plan["prompt"].startswith("he raps" + chr(10))
    assert 'word for word: "Dracula"' in done.shots[1].plan["prompt"] and "0.5 s into the shot" in done.shots[1].plan["lyrics"]
    assert done.shots[2].plan == {"prompt": "silence"}                       # no word starts in it
    assert apply_lyrics(done, words) == done                                  # repeatable
    assert apply_lyrics(done, words[:1]).shots[1].plan["prompt"] == "she raps"  # other words replace the earlier ones
    cast = apply_lyrics(apply_casting(ShotList(SimpleNamespace(fps=24), shots), _casting()), words)
    assert "grey ghoul" in cast.shots[0].plan["prompt"] and "Frankenstein woke" in cast.shots[0].plan["prompt"]


def test_a_shot_goes_to_the_character_the_planner_named_whatever_the_seconds():
    casting = _casting(shots={"SHOT_001": "witch", "SHOT_002": "Ghoul", "SHOT_003": "nobody", "SHOT_004": "witch", "bad": 5})
    assert casting["shots"] == {"SHOT_001": "witch", "SHOT_002": "ghoul", "SHOT_004": "witch"}      # a name is understood, a character that does not exist is dropped
    shots = [_shot(1, 0, 24), _shot(2, 24, 48), _shot(3, 48, 72), _shot(4, 72, 96)]
    cast = cast_shots(casting, shots, 24)
    assert [cast[f"SHOT_{i:03d}"]["character_id"] for i in range(1, 5)] == ["witch", "ghoul", "ghoul", "witch"]   # SHOT_003 names nobody: its seconds decide
    assert cast["SHOT_001"]["name"] == "Witch" and _casting()["shots"] == {}


def test_spoken_lines_are_written_as_spoken_not_sung():
    from dataclasses import dataclass
    from majoor_videotools.core.casting import apply_lyrics

    @dataclass(frozen=True)
    class Shot:
        shot_id: str
        start_frame: int
        end_frame_exclusive: int
        plan: dict | None = None

    @dataclass(frozen=True)
    class ShotList:
        source: SimpleNamespace
        shots: tuple

    words = [{"word": "Buy", "start": .4, "end": .6}, {"word": "now", "start": .7, "end": 1.0}]
    done = apply_lyrics(ShotList(SimpleNamespace(fps=24), (Shot("SHOT_001", 0, 48, {"prompt": "she smiles"}),)), words, spoken=True)
    assert 'Spoken in this shot, word for word: "Buy now"' in done.shots[0].plan["prompt"] and "sung" not in done.shots[0].plan["prompt"]


def test_the_words_replace_themselves_even_on_an_empty_prompt_and_shot_ids_may_be_in_any_case():
    from dataclasses import dataclass
    from majoor_videotools.core.casting import apply_lyrics

    @dataclass(frozen=True)
    class Shot:
        shot_id: str
        start_frame: int
        end_frame_exclusive: int
        plan: dict | None = None

    @dataclass(frozen=True)
    class ShotList:
        source: SimpleNamespace
        shots: tuple

    words = [{"word": "Go", "start": .2, "end": .4}]
    once = apply_lyrics(ShotList(SimpleNamespace(fps=24), (Shot("SHOT_001", 0, 48, {}),)), words)
    assert apply_lyrics(once, words) == once and once.shots[0].plan["prompt"].count("word for word") == 1
    casting = _casting(shots={"shot_001": "witch"})
    assert cast_shots(casting, [_shot(1, 0, 24)], 24)["SHOT_001"]["character_id"] == "witch"
