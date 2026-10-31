import pytest

from majoor_videotools.core import skills as sk
from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.profiles import DIALS, list_profiles, profile_text

NL = chr(10)


def test_the_shipped_profiles_are_skill_files():
    assert set(list_profiles()) == {"micro_emotion_pov", "slowed_dream", "hype_beat_drop", "viral_aura_farming", "beauty_premium", "narrative_cinematic", "product_advertising", "music_video", "glow_up", "outfit_change", "kinetic_lyrics", "punch_text_anime", "editorial_layouts", "camera_rec_hud", "cutout_collage", "lipsync_rap", "brand_film_noir"}
    for name in list_profiles():
        skill = sk.load_skill("profile_" + name)
        assert skill.kind == "profile" and skill.meta["length"] and all(skill.meta[d] in DIALS[d] for d in DIALS), name
        text = profile_text(name)
        assert text.startswith(f"EDITING PROFILE: {skill.name}") and "the BRIEF and any instruction of the user win" in text
        assert "Rhythm:" in text and "Camera:" in text and "Art direction:" in text and "Cut density:" in text and "Narrative coherence:" in text


def test_a_dial_replaces_the_profile_value_and_auto_keeps_it():
    base = profile_text("narrative_cinematic")
    assert "Cut density: low," in base and "Narrative coherence: high," in base
    tuned = profile_text("narrative_cinematic", cut_density="high", narrative_coherence="auto")
    assert "Cut density: high," in tuned and "Narrative coherence: high," in tuned


def test_no_profile_is_empty_and_bad_values_are_refused():
    assert profile_text("none") == ""
    with pytest.raises(MajoorError, match="Unknown profile"):
        profile_text("western")
    with pytest.raises(MajoorError, match="cut_density 'wild'"):
        profile_text("music_video", cut_density="wild")


def test_the_profile_is_in_the_system_prompt_before_the_extra_instructions():
    planner = sk.load_skill("timeline_planner")
    text, _ = sk.compose(planner, sk.module_states(planner), None, "Brand: Aura.", profile_text("product_advertising"))
    assert text.index("ROLE") < text.index("EDITING PROFILE: Product / Advertising") < text.index("EXTRA INSTRUCTIONS FROM THE USER")
    plain, _ = sk.compose(planner, sk.module_states(planner), None, "Brand: Aura.")
    assert "EDITING PROFILE" not in plain


def test_edit_skills_builds_the_profile_but_not_for_a_music_skill():
    pytest.importorskip("comfy_api.latest")
    from majoor_videotools.nodes.edit_skills import _build  # imports comfy_api: only inside ComfyUI

    _, planner, _ = _build("timeline_planner", True, True, True, "all", 0, 0, "auto", 1, "", "", "viral_aura_farming", {"cut_density": "low"})
    assert "Viral / Aura Farming" in planner and "Cut density: low," in planner and "Transition intensity: bold," in planner
    _, music, _ = _build("music_brief_from_plan", True, True, True, "all", 0, 0, "auto", 1, "", "", "viral_aura_farming", {})
    assert "EDITING PROFILE" not in music


def test_a_music_gets_the_music_direction_of_the_profile_and_the_density_of_the_cuts():
    from majoor_videotools.core.profiles import music_text

    text = music_text("viral_aura_farming")
    assert "bass-forward" in text and "fallback only" in text and "dense" in text and "camera" not in text.lower()
    assert "a steady pace" in music_text("viral_aura_farming", cut_density="medium")
    assert music_text("none") == ""
    for pid in list_profiles():
        assert "Music: " in music_text(pid), pid
    with pytest.raises(MajoorError, match="Unknown profile"):
        music_text("western")


def test_the_dials_the_user_chose_are_written_without_a_profile_and_win_over_the_profile_text():
    from majoor_videotools.core.profiles import profile_text

    assert profile_text("none") == "" and profile_text("none", cut_density="auto") == ""
    settings = profile_text("none", cut_density="low", transition_intensity="subtle")
    assert settings.startswith("EDITING SETTINGS") and "Cut density: low" in settings and "no flash, whip, strobe" in settings
    mixed = profile_text("hype_beat_drop", transition_intensity="subtle")
    assert "Transition intensity: subtle" in mixed and "win over the profile text above" in mixed and "transition intensity" in mixed.split("win over")[0]
    assert "win over the profile text" not in profile_text("hype_beat_drop")
