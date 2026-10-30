"""PR #5 G7: invalid effects must fail before rendering (no media/GPU needed)."""
from fractions import Fraction

import pytest

from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.fx import _number, parse_fx


def effect_rows(value):
    return [
        {"speed": value}, {"speed_ramp": [1, value]}, {"zoom": [1, value]},
        {"focus": [value, 1]}, {"transition": {"type": "flash", "frames": value}},
        {"transition": {"type": "flash", "duration": value}},
        *({"text": {"content": "TEST", key: value}} for key in ("size", "repeat", "rotate", "start", "end")),
        *({"overlay": {"source": "self", key: value}} for key in ("offset", "opacity", "scale", "zoom", "focus")),
        {"split": {"panels": [{"source": "self", "offset": value}]}},
        {"sub_cuts": [{"duration_frames": 24, "start": value}]},
        {"sub_cuts": [{"duration_frames": value}]},
        {"refs": [value]},
    ]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), "NaN", "Infinity", "-inf", True, None, [], {}, 10**400])
def test_invalid_numbers_are_rejected_with_shot_context(value):
    for row in effect_rows(value):
        if value is None and row == {"sub_cuts": [{"duration_frames": 24, "start": None}]}:
            continue  # Existing contract: null start means automatic sequential placement.
        with pytest.raises(MajoorError, match="SHOT_007"):
            parse_fx(row, "SHOT_007", Fraction(24), lambda value, fps: 24)


@pytest.mark.parametrize("value,expected", [(-5, .1), (20, 8), (1.25, 1.25), ("2", 2)])
def test_finite_clamp_contract_is_preserved(value, expected):
    assert _number(value, "speed", "SHOT_007", .1, 8) == expected


def test_strict_finite_range_still_raises():
    with pytest.raises(MajoorError, match="between"):
        _number(20, "refs", "SHOT_007", 1, 9, strict=True)


@pytest.mark.parametrize("name", ["output_fps", "music_volume", "sfx_volume", "shot_volume", "music_fade", "duck", "loudness_target"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, 10**400])
def test_invalid_assembly_numbers_fail_before_media_io(tmp_path, name, value):
    from majoor_videotools.core.assembler import AssemblyOptions, assemble_shots
    from majoor_videotools.core.errors import AssemblyError

    options = AssemblyOptions()
    setattr(options, name, value)
    with pytest.raises(AssemblyError, match=name):
        assemble_shots(None, tmp_path, options)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_stored_fx_are_revalidated(value):
    from majoor_videotools.core.fx import validate_stored_fx

    with pytest.raises(MajoorError, match="SHOT_007"):
        validate_stored_fx({"sub_cuts": [{"frames": 24, "speed": value}]}, "SHOT_007", Fraction(24))
