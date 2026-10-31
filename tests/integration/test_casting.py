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
