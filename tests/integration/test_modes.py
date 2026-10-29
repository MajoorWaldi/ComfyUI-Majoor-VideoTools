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
    assert modes.MAX_REFERENCES == 5 and list(modes.MODES) == ["creative", "remix_replace"]
    settings = modes.all_settings()
    assert set(settings) == set(modes.MODES)
    assert all(s["enhancer"].strip() for s in settings.values())
    assert "<Video 1>" in settings["remix_replace"]["enhancer"] and "<Picture 1>" in settings["creative"]["enhancer"] and "<Video 1>" in settings["creative"]["enhancer_from_video"]
    assert {m: s["from_video"] for m, s in settings.items()} == {"creative": False, "remix_replace": True}  # the remix always works on a video
    remix, creative = settings["remix_replace"], settings["creative"]  # no planner in the remix: its blocks have their own analyzer and director
    assert 0 <= remix["pose_strength"] <= 1 and "<Picture 1>" in remix["remix_instruction"]
    for profile in (creative["profile"], creative["profile_from_video"]):
        assert profile in ("none", *list_profiles())
    assert creative["genre"] in ("all", "none", *GENRES) and isinstance(creative["reference_mode"], bool)
    assert creative["extra_instructions"] and "EDIT RHYTHM" in creative["from_video_instructions"]


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


def test_the_style_default_is_not_a_profile():
    assert modes.STYLE_DEFAULT not in list_profiles()


def test_a_camera_look_is_a_sentence_for_the_planner_and_none_is_nothing():
    from majoor_videotools.core.camera import CAMERAS, camera_text

    assert camera_text("none") == "" and camera_text("not_a_look") == ""
    for look, phrase in CAMERAS.items():
        assert phrase.startswith("shot ") and camera_text(look).startswith("CAMERA LOOK: ") and phrase in camera_text(look), look
