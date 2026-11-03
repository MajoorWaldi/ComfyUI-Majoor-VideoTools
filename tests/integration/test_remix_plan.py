"""The plan of a remix laid on the shots of its source, the shots kept as in the source, and the Remix graphs that use them."""
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.media_probe import probe
from majoor_videotools.core.paths import ProjectStore
from majoor_videotools.core.remix_plan import apply_remix_plan, parse_remix_plan, plan_summary
from majoor_videotools.core.render_source import parse_render_source, render_planned_source

WORKFLOWS = Path(__file__).resolve().parents[2] / 'HyperKut Studio/workflows/remix'


@dataclass(frozen=True)
class Shot:
    shot_id: str
    start_frame: int
    end_frame_exclusive: int
    plan: dict | None = None
    target_duration_seconds: float = 1.0


@dataclass(frozen=True)
class ShotList:
    source: SimpleNamespace
    shots: tuple


def _source(*plans):
    return ShotList(SimpleNamespace(fps=24), tuple(Shot(f'SHOT_{i:03d}', (i - 1) * 48, i * 48, plan) for i, plan in enumerate(plans, 1)))


ANSWER = '''Here is the plan:
```json
{"story": "A courier crosses the night city.",
 "characters": [{"id": "Courier", "name": "Courier", "picture": 1}, {"id": "stranger", "name": "Stranger", "picture": 0, "look": "a tall woman in a grey coat"}],
 "shots": [
  {"id": "shot_001", "shows": "a man runs", "source": "generate", "cast": "courier", "location": "a metro stairway", "prompt": "He runs down with the letter."},
  {"id": "SHOT_002", "shows": "a neon sign", "source": "original"},
  {"id": "SHOT_003", "source": "title", "title_text": "DAWN"},
  {"id": "SHOT_404", "prompt": "an invented shot"}]}
```'''


def test_the_plan_writes_who_where_and_the_story_line_without_touching_the_cuts():
    source = _source({}, None, {'prompt': 'keep his jacket'})
    planned = apply_remix_plan(source, parse_remix_plan(ANSWER), places=True)
    first, second, third = planned.shots
    assert [(s.start_frame, s.end_frame_exclusive) for s in planned.shots] == [(s.start_frame, s.end_frame_exclusive) for s in source.shots]
    assert first.plan['cast'] == {'character_id': 'courier', 'name': 'Courier', 'picture': 1}
    assert first.plan['location'] == 'a metro stairway'
    assert first.plan['prompt'].splitlines() == ['Who: the person of <Picture 1> (Courier) takes the place of the person the source shows.',
                                                 'Place: a metro stairway.', 'He runs down with the letter.']
    assert second.plan['render_source'] == {'kind': 'original'}
    assert third.plan['render_source'] == {'kind': 'graphic', 'text': 'DAWN', 'color': '#101018'}
    assert third.plan['prompt'] == 'keep his jacket'  # the correction written before is kept under the plan
    assert 'SHOT_404' not in plan_summary(parse_remix_plan(ANSWER), planned) and 'STORY OF THE REMIX' in plan_summary(parse_remix_plan(ANSWER), planned)


def test_a_new_plan_replaces_the_earlier_one_and_options_off_write_nothing():
    planned = apply_remix_plan(_source({}, {}, {}), parse_remix_plan(ANSWER), places=True)
    again = apply_remix_plan(planned, parse_remix_plan('{"shots": [{"id": "SHOT_001", "prompt": "He walks."}]}'), places=True)
    assert again.shots[0].plan['prompt'] == 'He walks.' and 'cast' not in again.shots[0].plan and 'location' not in again.shots[0].plan
    assert 'render_source' not in again.shots[1].plan
    plain = apply_remix_plan(_source({}, {}, {}), parse_remix_plan(ANSWER), cast=False, places=False, keep_sources=False)
    assert all('cast' not in s.plan and 'location' not in s.plan and 'render_source' not in s.plan for s in plain.shots)


def test_an_answer_without_json_is_refused():
    with pytest.raises(MajoorError):
        parse_remix_plan('I cannot plan this.')


def test_a_kept_shot_is_rendered_from_its_own_clip_with_its_exact_frames(tmp_path, fixtures):
    assert parse_render_source({'kind': 'original'}) == {'kind': 'original'}
    shot = Shot('SHOT_001', 0, 24, {'render_source': {'kind': 'original'}}, target_duration_seconds=1.0)
    path = render_planned_source(ProjectStore(tmp_path, 'p_0123456789ab'), shot, 24, 128, 128, video=Path(fixtures['one']))
    assert probe(path).frame_count == 24
    with pytest.raises(MajoorError, match='not supplied'):
        render_planned_source(ProjectStore(tmp_path, 'p_0123456789ab'), shot, 24, 128, 128)


def test_the_remix_graphs_plan_judge_remember_and_keep_shots():
    stage1, shot, local = (json.loads((WORKFLOWS / f'{name}.api.json').read_text(encoding='utf-8')) for name in ('stage1', 'shot', 'local'))
    slots = json.loads((WORKFLOWS / 'slots.json').read_text(encoding='utf-8'))
    kinds = lambda graph: {node['class_type'] for node in graph.values()}
    assert {'MajoorRemixPlan', 'MajoorTranscribeVoice', 'MajoorSaveProjectLyrics', 'MajoorCameraMoves'} <= kinds(stage1)
    assert stage1['RP']['inputs']['skill'] == 'remix_planner' and stage1['RM']['inputs']['plan_json'] == ['RS', 0]
    assert stage1['p1']['inputs']['shot_list'] == ['CV', 0]
    assert {'MajoorShotMemory', 'MajoorSaveShotMemory', 'MajoorTakeCheck', 'MajoorCheckPlate'} <= kinds(shot)
    assert shot['JS']['inputs']['skill'] == 'take_judge' and shot['116']['inputs']['on_false'] == ['J', 0]
    assert slots['shot']['seed'] == [['91:155', 'noise_seed']] and slots['shot']['seed_b'] == [['108:155', 'noise_seed']]  # take B has its own seed
    assert local['153']['class_type'] == 'MajoorShotSource' and local['153']['inputs']['original_video'] == ['75', 0]
    for name in ('remix_plan', 'remix_cast', 'source_words', 'remix_camera', 'plates', 'planning_instructions'):
        assert name in slots['stage1']
    assert {'judge', 'plates', 'pictures_before'} <= slots['shot'].keys() and 'local' in slots


def test_a_person_given_a_picture_that_does_not_exist_is_described_instead():
    plan = parse_remix_plan('{"characters": [{"id": "a", "name": "A", "picture": 3, "look": "a red coat"}], "shots": [{"id": "SHOT_001", "cast": "a"}]}', pictures=2)
    assert plan['characters'][0]['picture'] == 0
    shot = apply_remix_plan(_source({}), plan).shots[0]
    assert shot.plan['prompt'] == 'Who: A, a red coat' and shot.plan['cast']['picture'] == 0


def test_a_created_timeline_has_no_original_shot_to_keep():
    from majoor_videotools.core.template import parse_plan
    plan = parse_plan(json.dumps({'shots': [{'duration': 1, 'prompt': 'x', 'render_source': {'kind': 'original'}}]}), 24, '1:1', 128)
    assert plan.shots[0].render_source == {'kind': 'generated'}


def _ran(graph, known):
    """The nodes that run, ComfySwitchNode being lazy and every other node eager; `known` gives the booleans of computed switches."""
    ran = set()
    def visit(key):
        if key in ran:
            return
        ran.add(key)
        node = graph[key]
        if node['class_type'] == 'ComfySwitchNode':
            link = node['inputs']['switch']
            if isinstance(link, list):
                visit(str(link[0]))
                flag = known.get((str(link[0]), link[1]), graph[str(link[0])]['inputs'].get('value'))
            else:
                flag = link  # a fixed switch
            branch = node['inputs'].get('on_true' if flag else 'on_false')
            if isinstance(branch, list):
                visit(str(branch[0]))
            return
        for value in node['inputs'].values():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[1], int):
                visit(str(value[0]))
    for key, node in graph.items():
        if node['class_type'] in ('MajoorSaveProjectInfo', 'MajoorSaveShotMemory', 'MajoorSaveProjectLyrics'):
            visit(key)
    return ran


def test_a_remix_without_plan_or_words_runs_no_language_model_and_decodes_no_whole_video():
    stage1 = json.loads((WORKFLOWS / 'stage1.api.json').read_text(encoding='utf-8'))
    quiet = _ran(stage1, {})
    assert not {'80:9015', 'RT', '43'} & quiet and not any(stage1[k]['class_type'] == 'GetVideoComponents' for k in quiet)
    stage1['RB']['inputs']['value'] = stage1['VT']['inputs']['value'] = True
    assert {'80:9015', 'RT', '43', 'VX1'} <= _ran(stage1, {})
    assert stage1['80:9014']['inputs']['extra_instructions'] == ['PX', 0] and stage1['PX']['inputs']['string_a'] == ['77', 0]


@pytest.mark.parametrize('judge,check,failed', [(False, False, False), (False, True, True), (True, True, True)])
def test_take_b_runs_only_for_a_failed_check_or_best_of_two(judge, check, failed):
    shot = json.loads((WORKFLOWS / 'shot.api.json').read_text(encoding='utf-8'))
    shot['JBOOL']['inputs']['value'] = judge
    ran = _ran(shot, {('115', 2): False, ('14', 0): check, ('110:9029', 0): failed, ('JN', 2): True, ('114', 2): False,
                      ('78:9022', 2): False, ('M1', 1): False, ('90:9027', 2): False})
    assert ('108:139' in ran) == (judge or (check and failed))
    assert ('JT' in ran) == judge and ('110:9028' in ran) == (check and not judge)
    assert '90:9024' not in ran  # no place picture without a place
