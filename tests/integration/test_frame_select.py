import pytest

from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.frame_select import every_n_frames, parse_frames


def test_frames_are_listed_in_the_order_written():
    assert parse_frames("0-3, 10, -1", 20) == [0, 1, 2, 3, 10, 19]
    assert parse_frames("0-10:5\n7, 7", 20) == [0, 5, 10, 7, 7]
    assert parse_frames("5-2", 20) == [5, 4, 3, 2]
    assert parse_frames("", 20) == [] and parse_frames(" , ", 20) == []
    assert parse_frames("-5--1", 20) == [15, 16, 17, 18, 19]


def test_a_number_of_frames_spread_evenly():
    assert parse_frames("~5", 21) == [0, 5, 10, 15, 20]
    assert parse_frames("~1", 21) == [10]
    assert parse_frames("~30", 4) == [0, 1, 2, 3]  # never more than the video has
    assert parse_frames("0, ~3", 9) == [0, 0, 4, 8]


@pytest.mark.parametrize("text", ["20", "-21", "a", "3:2", "0-5:0", "0-30", "~", "~0", "~x"])
def test_bad_frames_are_refused(text):
    with pytest.raises(MajoorError):
        parse_frames(text, 20)


def test_every_n_frames_reach_the_end_of_the_clip():
    assert every_n_frames(100, 10, 0, False) == list(range(0, 100, 10))
    assert every_n_frames(100, 10, 4, False) == [0, 10, 20, 30]  # stops before the end
    assert every_n_frames(100, 30, 0, True) == [0, 30, 60, 90, 99]  # the last frame is kept
    spread = every_n_frames(240, 2, 16, True)  # 120 candidates thinned to 16, first and last included
    assert len(spread) == 16 and spread[0] == 0 and spread[-1] == 239 and spread == sorted(set(spread))
    assert max(b - a for a, b in zip(spread, spread[1:])) <= 17
    assert every_n_frames(10, 3, 1, True) == [6]
    assert every_n_frames(5, 1, 16, True) == [0, 1, 2, 3, 4]  # fewer frames than max_frames: all of them
    assert every_n_frames(1, 8, 16, True) == [0]
    with pytest.raises(MajoorError):
        every_n_frames(0, 8)


def test_select_shot_samples_every_n_to_the_end():
    from majoor_videotools.core.frames import sample_indices

    assert sample_indices("every_n", 5, 48, 4, True) == [0, 12, 24, 36, 47]
    assert sample_indices("every_n", 4, 48, 4, False) == [0, 4, 8, 12]
    assert sample_indices("uniform", 3, 48) == [0, 24, 47]
