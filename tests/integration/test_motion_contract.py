import json

import pytest

from majoor_videotools.core.motion_contract import EVENT_ROLES, SOUND_EFFECTS, validate_motion_rows
from majoor_videotools.core.motion_scenes import style_layer
from majoor_videotools.core.motion_timing import shot_layers
from majoor_videotools.core.sfx import GAINS


@pytest.mark.parametrize("role", sorted(EVENT_ROLES))
def test_engine_accepts_supported_event_roles(role):
    assert style_layer({"type": "vector", "event_role": role})["event_role"] == role


@pytest.mark.parametrize("row", [{"event_role": "accent"}, {"sfx": "not-a-sound"}, {"sfx": True}])
def test_shared_motion_contract_rejects_unknown_role_and_sound(row):
    with pytest.raises(ValueError):
        validate_motion_rows([row])


def test_motion_sound_contract_matches_engine_palette():
    assert SOUND_EFFECTS == frozenset(GAINS)


@pytest.mark.parametrize("row", [{"event_role": "accent"}, {"sfx": "not-a-sound"}])
def test_engine_timeline_rejects_invalid_structure_before_time_resolution(row):
    with pytest.raises(ValueError):
        shot_layers(json.dumps([row]), "[]", 1, 24)
