import json

from majoor_videotools.core.plan_checks import check_plan
from majoor_videotools.core.edit_report import edit_report
from test_plan_checks import good, plan, PROMPT
from test_edit_report import video, manifest


def test_additional_words_are_rejected_even_with_authorized_title():
    shots = good()
    shots[0]['text'] = {'content': 'BUY NOW'}
    assert 'text_invented' in {i['code'] for i in check_plan(plan(shots), duration=15, text_allowed='NEW DROP')}


def test_motion_text_is_checked_when_text_is_off():
    shots = good()
    shots[-1].pop('text')
    shots[0]['motion'] = [{'type': 'text', 'content': 'BUY NOW'}]
    assert 'text_off' in {i['code'] for i in check_plan(plan(shots), duration=15, text_on=False)}


def test_one_frame_cuts_do_not_count_as_three_to_six_frame_burst():
    shots = good()
    shots[2]['sub_cuts'] = [{'duration': '1f'}] * 3 + [{'duration': '69f'}]
    assert 'burst' in {i['code'] for i in check_plan(plan(shots), duration=15, density='high', text_allowed='NEW DROP')}


def test_no_text_is_not_a_contradiction_when_text_is_off():
    shots = [{'id': 'SHOT_001', 'duration': 3, 'prompt': PROMPT + ' No text.'}]
    assert 'negation' not in {i['code'] for i in check_plan(plan(shots), duration=3, density='low', text_on=False)}


def test_review_samples_remain_inside_micro_cut_intervals(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'manifest.json').write_text(json.dumps(manifest([(.1, None), (.1, None), (5.8, None)])))
    result = edit_report(project, video(tmp_path / 'v.mp4'))
    assert 0 < result['sample_times'][0] < .1
    assert .1 < result['sample_times'][1] < .2
    assert .2 < result['sample_times'][2] < 6
    assert result['provenance']['cuts'] == 'manifest_target_durations'


def test_unified_readability_reserves_animation_time_without_changing_cuts():
    from majoor_videotools.core.motion_scenes import readability
    layer = {'type': 'text', 'content': 'NOUVELLE COLLECTION', 'start': 0, 'end': 1.2,
             'animation': 'fade', 'in_time': .35, 'out': 'fade'}
    result = readability([layer], 768, 1344, 3)
    assert any(w['kind'] == 'short_reading_window' for w in result['warnings'])
    assert layer['end'] == 1.2 and layer['content'] == 'NOUVELLE COLLECTION'


def test_shared_reading_budget_includes_entrance_hold_and_exit():
    from majoor_videotools.core.text_timing import reading_budget
    assert reading_budget('NEW DROP', .35, .18) == 1.53
    assert reading_budget('LA NOUVELLE COLLECTION EST ARRIVÉE', 0, 0) == 1.5
