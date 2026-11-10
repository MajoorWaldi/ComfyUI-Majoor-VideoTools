"""The prompts of the shots are long on purpose (500 words and more), and the skills carry the rules that make an edit hold: a hook, a plant and its payoff, what the model renders."""
import json

import pytest

from majoor_videotools.core import skills as sk
from majoor_videotools.core.remix_plan import parse_remix_plan
from majoor_videotools.core.story import story_fields

WRITERS = ("h3_shot_prompt_from_plan", "seedance_shot_prompt", "wan_shot_prompt", "ltx_shot_prompt", "seedance_remix_prompt", "remix_shot_prompt")


def _text(skill_id):
    skill = sk.load_skill(skill_id)
    return sk.compose(skill, sk.module_states(skill))[0]


@pytest.mark.parametrize("skill_id", ("h3_shot_prompt_from_plan", "seedance_shot_prompt", "ltx_shot_prompt", "wan_shot_prompt", "seedance_remix_prompt"))
def test_a_shot_writer_may_write_500_words_and_more(skill_id):
    text = _text(skill_id)
    assert any(f"to {n} words" in text for n in (500, 600, 800)), skill_id
    for old in ("200 to 300 words", "80 to 180 words", "80 to 200 words", "60 to 150 words", "70 to 160 words", "130-190"):
        assert old not in text, (skill_id, old)


def test_a_long_prompt_of_a_remix_shot_is_not_cut():
    prompt = "He turns his head. " * 150  # about 2,850 characters, 450 words
    plan = parse_remix_plan(json.dumps({"shots": [{"id": "SHOT_001", "prompt": prompt}], "characters": [{"id": "C1", "look": "a tall man " * 60}]}))
    assert len(plan["shots"]["SHOT_001"]["prompt"]) > 2800 and len(plan["characters"][0]["look"]) > 600


def test_a_long_story_field_is_kept():
    assert len(story_fields({"action": "x " * 600})["action"]) > 500


@pytest.mark.parametrize("skill_id", WRITERS + ("timeline_planner",))
def test_every_writer_says_what_the_video_model_can_render(skill_id):
    text = _text(skill_id).lower()
    assert "contact" in text and "state" in text and ("renders" in text or "render" in text), skill_id


@pytest.mark.parametrize("skill_id, word", [("seedance_shot_prompt", "Seedance 2.5"), ("wan_shot_prompt", "Wan 3.0"), ("ltx_shot_prompt", "LTX 2.5"), ("seedance_remix_prompt", "Edit mode")])
def test_each_model_has_its_own_render_rules(skill_id, word):
    text = _text(skill_id)
    assert "WHAT THE MODEL CAN RENDER" in text and f"- {word}:" in text


def test_the_story_planner_has_the_formula():
    text = _text("story_planner")
    for part in ("HOOK", "PLANT AND PAYOFF", "(plant:", "(payoff:", "MUTE TEST", "THE LAST IMAGE ANSWERS THE FIRST", "ONE INVENTED ELEMENT", "WHAT THE VIDEO MODELS CAN SHOW"):
        assert part in text, part
    assert "at most 550 words" in text and "at most 220 words" not in text
    assert "no similes" in text and "No narrator" in text


def test_the_ad_profile_asks_for_a_hook_a_proof_per_shot_and_a_payoff():
    skill = sk.load_skill("profile_product_advertising")
    body = skill.body if hasattr(skill, "body") else _text("profile_product_advertising")
    for part in ("Hook", "ONE visual proof", "Plant and payoff", "Product readable in every shot", "What renders"):
        assert part in body, part
