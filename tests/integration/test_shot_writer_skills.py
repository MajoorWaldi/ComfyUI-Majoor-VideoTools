import pytest

from majoor_videotools.core.generators import list_generators, load_generator
from majoor_videotools.core.skills import compose, load_skill, module_states, prompt_skills, user_message

API_WRITERS = ("seedance_shot_prompt", "wan_shot_prompt", "ltx_shot_prompt")


def test_every_model_names_a_skill_that_writes_its_prompt():
    for gid in list_generators("video"):
        gen = load_generator(gid)
        assert gen.prompt_skill, gid
        assert load_skill(gen.prompt_skill).kind in ("h3_writer", "shot_writer"), gid
        assert gen.prompt_skill in prompt_skills()


@pytest.mark.parametrize("skill_id", API_WRITERS)
def test_a_shot_writer_composes_with_its_modules(skill_id):
    skill = load_skill(skill_id)
    assert skill.kind == "shot_writer" and skill.meta["target"]
    plain, _ = compose(skill, module_states(skill, plate=False, dialogue=False))
    full, on = compose(skill, module_states(skill, plate=True, dialogue=True))
    assert "PLACE block" not in plain and "DIALOGUE block" not in plain and "no dialogue" in plain.lower()
    assert "PLACE block" in full and "DIALOGUE block" in full and "no dialogue" not in full.lower()
    assert "{{" not in plain and len(plain.split()) < 900  # the LLM of a shot gets a short prompt


def test_the_message_names_the_model_it_writes_for():
    assert user_message("a", "r", 2, shot_only=True).startswith("H3 INPUT MODE: Ref2VA")
    assert user_message("a", "r", 2, shot_only=True, target="Seedance 2.5").startswith("Seedance 2.5 INPUT MODE: reference")
    assert user_message("a", "r", 0, shot_only=True, target="LTX 2.5").startswith("LTX 2.5 INPUT MODE: text only")
    assert "Seedance 2.5 receives it" in user_message("", "", 1, voice=True, target="Seedance 2.5")
    assert "H3 receives it" in user_message("", "", 1, voice=True)


def test_the_reference_tags_of_the_skills_follow_the_models():
    assert "@Image1" in load_skill("seedance_shot_prompt").body and "@Audio1" in load_skill("wan_shot_prompt").body
    assert "@Image" not in load_skill("ltx_shot_prompt").body.replace("no tags", "")  # LTX has no reference tags


def test_a_remix_shot_has_its_own_writer_for_each_model_that_can_remix():
    from majoor_videotools.core.skills import skill_for_generator
    assert skill_for_generator("remix_shot_prompt", "seedance_2_5") == "seedance_remix_prompt"
    assert skill_for_generator("remix_shot_prompt", "minimax_h3") == "remix_shot_prompt"
    assert skill_for_generator("remix_shot_prompt", "") == "remix_shot_prompt"
    assert skill_for_generator("h3_shot_prompt_from_plan", "seedance_2_5") == "seedance_shot_prompt"  # a creation keeps its own writer
    assert skill_for_generator("timeline_planner", "seedance_2_5") == "timeline_planner"  # a planner is not a shot writer
    skill = load_skill("seedance_remix_prompt")
    assert skill.kind == "shot_writer" and skill.meta["target"] == "Seedance 2.5 edit"
    plain, _ = compose(skill, module_states(skill, dialogue=False))
    assert "@Video1" in plain and "Replace the person" in plain and "DIALOGUE" not in plain and len(plain.split()) < 900
    for gid in list_generators("video"):
        gen = load_generator(gid)
        assert (not gen.remix) or load_skill(gen.remix_prompt_skill).kind in ("h3_writer", "shot_writer"), gid
