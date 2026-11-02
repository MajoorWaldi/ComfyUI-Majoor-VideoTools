"""A camera move for every shot, no two in a row alike."""
from dataclasses import dataclass
from types import SimpleNamespace

from majoor_videotools.core.camera_moves import MARK, MOVES, add_camera_moves


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


def _list(*prompts):
    return ShotList(SimpleNamespace(fps=24), tuple(Shot(f"SHOT_{i:03d}", i * 48, (i + 1) * 48, {"prompt": text}) for i, text in enumerate(prompts, 1)))


def _moves(shot_list):
    return [(s.plan.get("camera_move") or [None])[0] for s in shot_list.shots]


def test_a_shot_that_names_no_move_gets_one_and_the_move_the_planner_wrote_is_kept():
    done = add_camera_moves(_list("He stands in a gallery.", "He stands in a gallery.", "A slow push-in on his face.", "He dances."))
    assert _moves(done) == ["slow push-in", "pull-back reveal", None, "lateral track"]
    assert done.shots[0].plan["prompt"] == "He stands in a gallery.\n" + MARK + "a slow push-in toward the subject."
    assert done.shots[2].plan["prompt"] == "A slow push-in on his face."


def test_the_same_move_twice_in_a_row_is_changed_and_a_fixed_camera_is_left_alone():
    assert _moves(add_camera_moves(_list("An orbit around her.", "Another orbit around her."))) == [None, "pull-back reveal"]
    fixed = _list("He stands still.", "He stands still.")
    assert add_camera_moves(fixed, "a fixed camera on a tripod, no movement") is fixed
    assert add_camera_moves(fixed, "caméra fixe, plan fixe") is fixed


def test_applying_it_again_gives_the_same_shot_list_and_the_seed_changes_the_moves():
    once = add_camera_moves(_list("a", "b", "c"), seed=0)
    assert _moves(once) == ["slow push-in", "pull-back reveal", "orbit"]
    assert add_camera_moves(once, seed=0) == once
    assert _moves(add_camera_moves(_list("a", "b", "c"), seed=5)) == ["handheld follow", "tilt-up", "crane"]
    assert len(MOVES) == 12


def test_the_word_track_of_a_music_does_not_count_as_a_camera_move():
    assert _moves(add_camera_moves(_list("He raps on the beat of the track."))) == ["slow push-in"]


def test_an_empty_prompt_takes_and_loses_its_move_cleanly():
    once = add_camera_moves(_list(""))
    assert once.shots[0].plan["prompt"] == MARK + "a slow push-in toward the subject."
    assert add_camera_moves(once) == once
