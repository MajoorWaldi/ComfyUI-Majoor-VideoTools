import dataclasses
import json

from majoor_videotools.core.fx import describe_shot
from majoor_videotools.core.story import story_fields, story_warnings
from majoor_videotools.core.template import create_template, parse_plan
from majoor_videotools.core.timeline_sources import merge_plans, plan_to_dict


STORY = dict(role='reveal', new_information='seal removed', start_state='cap attached',
             action='lift cap', end_state='cap beside bottle', handoff='cap stays removed')


def parse(rows):
    return parse_plan(json.dumps({'shots': rows}), 24, '16:9', 320)


def test_handoff_survives_parse_roundtrip_and_fixed_rhythm():
    plan = parse([{'id': 'A', 'duration': 2, 'story': STORY}])
    data = plan_to_dict(plan)
    assert data['shots'][0]['story'] == STORY
    merged, _ = merge_plans(json.dumps({'shots': [{'id': 'A', 'duration': 3}]}),
                            json.dumps(data), 24, '16:9', 320)
    assert merged['shots'][0]['story'] == STORY
    assert merged['shots'][0]['duration_frames'] == 72


def test_handoff_reaches_manifest_and_generator_brief(tmp_path):
    timeline = create_template(json.dumps({'shots': [{'duration': 1, 'story': STORY}]}),
                               tmp_path, fps=24, aspect_ratio='16:9', resolution=320,
                               profile='none', thumbnails=False)
    shot = timeline.shots[0]
    info, brief = describe_shot(shot.shot_id, 0, 1, 24, shot.plan, 24)
    assert shot.plan['story'] == info['story'] == STORY
    assert 'start state: cap attached' in brief
    assert 'handoff: cap stays removed' in brief


def test_legacy_plan_stays_optional_and_has_no_story_warning():
    plan = parse([{'duration': 1}, {'duration': 1}])
    assert 'story' not in plan_to_dict(plan)['shots'][0]
    assert not story_warnings(plan.shots)
    assert 'start state:' not in describe_shot('A', 0, 1, 24, {}, 24)[1]


def test_only_exact_complete_repeated_events_raise_advisory():
    plan = parse([{'duration': 1, 'story': STORY}, {'duration': 1, 'story': STORY}])
    assert len(story_warnings(plan.shots)) == 1
    changed = dataclasses.replace(plan.shots[1], story=STORY | {'action': 'spray once', 'start_state': STORY['end_state']})
    assert not story_warnings([plan.shots[0], changed])
    assert story_fields({'action': ['invalid'], 'end_state': ' fine ', 'unknown': 'x'}) == {'end_state': 'fine'}


def test_declared_prop_reset_is_advisory_and_explicit_loop_is_respected():
    from majoor_videotools.core.story import story_issues
    rows = [{'duration': 1, 'story': STORY}, {'duration': 1, 'story': STORY | {'action': 'spray once', 'new_information': 'mist appears'}}]
    assert story_issues(parse(rows).shots)[0][0] == 'story_reset'
    rows[1]['story']['role'] = 'flashback'
    assert not story_issues(parse(rows).shots)


def test_near_repeat_ignores_punctuation_but_preserves_negations_and_numbers():
    from majoor_videotools.core.story import _near
    assert _near('Cap beside the bottle.', 'cap beside the bottle')
    assert _near('The same gloved hand slowly lifts the bottle into the light', 'The same gloved hand gently lifts the bottle into the light')
    assert not _near('the same hand does not lift the cap from the bottle', 'the same hand does lift the cap from the bottle')
    assert not _near('the same hand rotates the bottle 90 degrees under the light', 'the same hand rotates the bottle 180 degrees under the light')


def test_unexplained_declared_handoff_is_advisory_and_allows_an_explanation():
    from majoor_videotools.core.story import story_issues
    next_story = {'start_state': 'bottle on a sunny beach', 'action': 'hold still'}
    rows = [{'duration': 1, 'story': STORY}, {'duration': 1, 'story': next_story}]
    assert story_issues(parse(rows).shots)[0][0] == 'story_handoff'
    next_story['new_information'] = 'A deliberate time jump relocates the product to the shore'
    assert not story_issues(parse(rows).shots)
    next_story.pop('new_information')
    next_story['start_state'] = 'cap beside bottle with the atomizer exposed'
    assert not story_issues(parse(rows).shots)


def test_automatic_burst_keeps_labels_and_screen_direction():
    from majoor_videotools.core.timeline_sources import ensure_burst
    rows = [{'duration': 2, 'prompt': prompt} for prompt in
            ('establish bottle', 'detail of readable label', 'payoff')]
    result = json.loads(ensure_burst(json.dumps({'shots': rows}), 'high'))
    cuts = result['shots'][1]['sub_cuts']
    assert len(cuts) == 5 and not any(c.get('flip') for c in cuts)
    assert sum(c['duration'] for c in cuts) == 2
