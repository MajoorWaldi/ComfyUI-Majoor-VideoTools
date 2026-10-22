import json
from pathlib import Path

import pytest

from majoor_videotools.core import modes
from majoor_videotools.core import skills as sk
from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.profiles import list_profiles
from majoor_videotools.core.skills import GENRES

RECIPES = Path(__file__).resolve().parents[2] / "recipes"


def test_every_mode_has_a_skill_that_the_planner_understands():
    assert modes.MAX_REFERENCES == 5
    settings = modes.all_settings()
    assert set(settings) == set(modes.MODES)
    assert all(s["enhancer"].strip() for s in settings.values())
    assert "<Video 1>" in settings["remix_replace"]["enhancer"] and "<Picture 1>" in settings["image_to_edit"]["enhancer"]
    assert {m: s["reference_video"] for m, s in settings.items()} == {"image_to_edit": False, "reference_to_edit": True, "music_to_edit": False, "text_to_edit": False, "remix_replace": True}
    for mode, setting in settings.items():
        if mode == "remix_replace":  # no planner: its blocks have their own analyzer and director
            assert 0 <= setting["pose_strength"] <= 1 and "<Picture 1>" in setting["remix_instruction"]
            continue
        assert setting["profile"] in ("none", *list_profiles()), mode
        assert setting["genre"] in ("all", "none", *GENRES), mode
        assert isinstance(setting["reference_mode"], bool) and setting["extra_instructions"], mode


def test_an_unknown_mode_is_refused():
    with pytest.raises(MajoorError, match="Unknown mode"):
        modes.mode_settings("western")


def test_the_prompts_of_the_recipes_are_skills_of_the_folder():
    known = set(sk.prompt_skills())
    seen = 0
    for recipe in RECIPES.glob("*.json"):
        data = json.loads(recipe.read_text(encoding="utf-8"))
        for sg in data["definitions"]["subgraphs"]:
            for node in sg["nodes"]:
                if node["type"] == "MajoorEditSkills":
                    seen += 1
                    assert node["widgets_values"][0] in known, (recipe.name, node["widgets_values"][0])
    assert seen >= 5  # the writer of the plan recipes, the analyzer and the director of the remix recipes


def test_the_presets_name_three_modes_and_the_style_is_a_profile():
    assert set(modes.PRESETS.values()) <= set(modes.MODES) and len(modes.PRESETS) == 3
    assert modes.ADVANCED not in modes.PRESETS and modes.STYLE_DEFAULT not in list_profiles()
