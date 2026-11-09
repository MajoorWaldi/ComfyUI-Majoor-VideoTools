import pytest

from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.generators import check_shot, describe, generation_frames_for, generation_seconds_for, list_generators, load_generator
from majoor_videotools.core.template import PROFILES, generation_frames


def test_registry_lists_the_video_models():
    assert {"minimax_h3", "seedance_2_5", "wan_3_0", "ltx_2_5_fast", "ltx_2_5_pro"} <= set(list_generators("video"))
    assert PROFILES[0] == "none" and "seedance_2_5" in PROFILES
    for g in list_generators():
        assert describe(g)["id"] == g


def test_frame_grid_is_the_old_h3_rule():
    assert generation_frames(72, "minimax_h3") == 124
    assert generation_frames(125, "minimax_h3") == 141
    assert generation_frames(360, "minimax_h3") == 362
    assert generation_frames(72, "none") == 72


def test_seconds_models_round_up_to_whole_seconds():
    assert generation_frames(72, "seedance_2_5", 24) == 96  # 3 s asked, the model starts at 4 s
    assert generation_frames(100, "seedance_2_5", 25) == 100  # exactly 4 s
    assert generation_frames(101, "seedance_2_5", 25) == 125  # 5 s
    assert generation_frames(130, "wan_3_0", 24) == 144  # 5.4 s -> 6 s
    assert generation_seconds_for("seedance_2_5", 130, 24) == 6.0
    assert generation_seconds_for("minimax_h3", 130, 24) is None


def test_listed_durations_pick_the_next_allowed_value():
    assert generation_seconds_for("ltx_2_5_pro", 7 * 24, 24) == 8.0  # 7 s is not offered
    assert generation_seconds_for("ltx_2_5_fast", 11 * 24, 24) == 12.0
    assert generation_seconds_for("ltx_2_5_pro", 20 * 24, 24) == 10.0  # capped at its maximum


def test_a_seconds_model_needs_the_fps():
    with pytest.raises(MajoorError, match="fps"):
        generation_frames(72, "seedance_2_5")


def test_check_shot_reports_what_the_model_cannot_do():
    assert check_shot("seedance_2_5", "S1", 24 * 10, 24, images=3) == []
    assert "longer" in check_shot("ltx_2_5_pro", "S1", 24 * 12, 24)[0]
    assert "reference images" in check_shot("wan_3_0", "S2", 48, 24, images=11)[0]
    assert check_shot("minimax_h3", "S3", 48, 24, images=40) == []  # unknown limit: nothing to say


def test_unknown_or_invalid_ids_are_refused():
    for bad in ("nope", "../x", "Seedance"):
        with pytest.raises(MajoorError):
            load_generator(bad)


def test_only_the_models_that_edit_a_video_can_remix():
    assert load_generator("seedance_2_5").remix and "edit" in load_generator("seedance_2_5").tasks
    assert load_generator("minimax_h3").remix and load_generator("minimax_h3").tasks == ("reference",)  # H3 remixes with its pose map, not through an edit task
    assert not load_generator("wan_3_0").remix and not load_generator("ltx_2_5_pro").remix
    assert describe("seedance_2_5")["remix"] is True and describe("seedance_2_5")["tasks"] == ["reference", "edit"]
