import json
import pytest
from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.motion import parse_layers
from majoor_videotools.core.template import parse_plan


@pytest.mark.parametrize('shape', ['line', 'dot', 'ring'])
def test_unambiguous_vector_type_alias_preserves_geometry_and_timing(shape):
    row = {'type': shape, 'start': .3, 'end': 1.8, 'at': [.12,.8], 'to': [.32,.8], 'color': '#c9b3fb', 'animation': 'draw'}
    assert parse_layers(json.dumps([row]), 2) == parse_layers(json.dumps([{**row, 'type':'vector', 'shape':shape}]), 2)
    result = parse_plan(json.dumps({'shots':[{'duration':2,'motion':[row]}]}),24,'9:16',320)
    assert len(result.shots) == 1


def test_unknown_shapes_and_conflicting_aliases_still_fail():
    with pytest.raises(MajoorError, match='conflicting'):
        parse_layers('[{"type":"line","shape":"ring"}]', 2)
    with pytest.raises(MajoorError, match='unknown type'):
        parse_layers('[{"type":"invented_shape"}]', 2)
