import json
from majoor_videotools.core.hyperframes import parse_direction
from majoor_videotools.core.timeline_sources import ensure_burst
from majoor_videotools.core.story import story_fields
from majoor_videotools.core.prompt_guard import clean_plan_text

def test_canonical_directions_and_quiet_defaults():
    for name in ('energetic', 'minimal', 'editorial'):
        assert parse_direction(name)['preset'] == name
    assert parse_direction('minimal')['reactive'] is False
    assert parse_direction('minimal')['intensity'] < .2
    assert parse_direction('{"preset":"minimal","reactive":true,"intensity":0.8}')['intensity'] == .8

def test_essential_actions_survive_and_safe_inserts_can_burst():
    shots = [{'duration':3,'prompt':'Opening'}, {'duration':4,'prompt':'Removes the cap in one continuous action'}, {'duration':4,'prompt':'Press atomizer once'}, {'duration':4,'prompt':'End'}]
    assert not any(s.get('sub_cuts') for s in json.loads(ensure_burst(json.dumps({'shots':shots}), 'high'))['shots'])
    shots.insert(2, {'duration':2,'prompt':'Macro glass texture'})
    result = json.loads(ensure_burst(json.dumps({'shots':shots}), 'medium'))['shots']
    assert result[2].get('sub_cuts') and not result[1].get('sub_cuts')
    assert story_fields({'protect_action':True}) == {'protect_action':True}

def test_generation_exclusions_are_preserved():
    shot={'prompt':'One continuous take, no cuts. No text or logos.', 'image_prompt':'Bottle, no logos.'}
    result, removed=clean_plan_text(json.dumps({'shots':[shot]}))
    assert json.loads(result)['shots'][0] == shot and removed == []
