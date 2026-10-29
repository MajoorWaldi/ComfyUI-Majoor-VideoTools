import json
import pytest
from majoor_videotools.core.motion_timing import shot_layers, preview_times
from majoor_videotools.core.template import parse_plan
from majoor_videotools.core.timeline_sources import plan_to_dict, merge_plans

TIMELINE = '[{"id":"A","start":0,"duration":2},{"id":"B","start":2,"duration":2}]'


def test_planner_seconds_suffix_resolves_inside_its_shot():
    rows, _ = shot_layers('[{"shot_id":"B","start":" 1.5s ","end":"2.0s"}]', TIMELINE, 4, 24)
    assert (rows[0]['start'], rows[0]['end']) == (3.5, 4)
    with pytest.raises(ValueError):
        shot_layers('[{"start":"1.5px"}]', '[]', 4, 24)


def test_local_percentages_snap_to_real_attack_without_spilling():
    rows, report = shot_layers('[{"shot_id":"B","type":"box","start":"10%","end":"80%","sync":"onset"}]', TIMELINE, 4, 24, [1.99, 2.29, 3.8])
    assert rows[0]['start'] == pytest.approx(55 / 24)
    assert rows[0]['end'] == pytest.approx(86 / 24)
    assert report[0]['matched']
    assert 'shot_id' not in rows[0] and 'sync' not in rows[0]


def test_no_attack_keeps_timing_and_absolute_legacy_layers_stay_absolute():
    rows, report = shot_layers('[{"shot_id":"B","start":0.5,"end":1,"sync":"onset"},{"start":0.5,"end":1}]', TIMELINE, 4, 24)
    assert (rows[0]['start'], rows[0]['end']) == (2.5, 3)
    assert (rows[1]['start'], rows[1]['end']) == (.5, 1)
    assert not report[0]['matched']
    rows, report = shot_layers('[{"shot_id":"B","start":0,"end":0.5,"sync":"onset"}]', TIMELINE, 4, 24, [1.99])
    assert rows[0]['start'] == 2 and not report[0]['matched']


@pytest.mark.parametrize('layer', [{'shot_id':'missing'}, {'shot_id':'B','start':1,'end':3}, {'start':float('nan')}, {'sync':'invented'}])
def test_invalid_timing_is_rejected(layer):
    with pytest.raises(ValueError):
        shot_layers(json.dumps([layer]), TIMELINE, 4, 24)


def test_preview_samples_cover_shots_and_settled_animation_with_bounded_cost():
    times = preview_times([{'start':1,'end':2,'in_time':.3}], [], TIMELINE, 4, 24)
    assert any(1.3 <= t <= 1.4 for t in times) and 3 in times
    assert all(0 <= t < 4 for t in times)
    assert len(preview_times([{'start':i/100,'end':4} for i in range(120)], [], TIMELINE,4,24)) <= 16


def test_planner_preserves_optional_motion_without_changing_legacy_plan():
    motion=[{'type':'brackets','start':'10%','end':'90%','animation':'draw'}]
    plan=parse_plan(json.dumps({'shots':[{'id':'A','duration':2,'motion':motion}]}),24,'16:9',320)
    assert plan.shots[0].motion == motion
    assert plan_to_dict(plan)['shots'][0]['motion'] == motion
    merged, _ = merge_plans('{"shots":[{"id":"A","duration":2}]}', json.dumps({'shots':[{'id':'A','duration':2,'motion':motion}]}),24,'16:9',320)
    assert merged['shots'][0]['motion'] == motion
    assert not parse_plan('{"shots":[{"duration":2}]}',24,'16:9',320).shots[0].motion
