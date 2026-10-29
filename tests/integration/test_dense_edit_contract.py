import json
from majoor_videotools.core.timeline_sources import ensure_burst,is_dense_edit,edit_segment_frames
from majoor_videotools.core.template import parse_plan
from majoor_videotools.core.plan_checks import check_plan


def test_twenty_independent_short_inserts_are_dense_without_fake_crop_bursts():
    rows=[{'id':f'SHOT_{i+1:03d}','duration':.75,'prompt':f'Detail {i+1}'} for i in range(20)]
    text=json.dumps({'shots':rows})
    assert len(parse_plan(text,24,'9:16',256).shots)==20
    assert is_dense_edit(rows)
    assert ensure_burst(text,'high')==text
    assert not any(x['code']=='burst' for x in check_plan(text,duration=15,density='high',text_on=False))


def test_slow_existing_cuts_do_not_block_other_safe_accents():
    rows=[{'id':str(i),'duration':3,'prompt':'Macro texture'} for i in range(5)]
    rows[1]['sub_cuts']=[{'duration':1.5},{'duration':1.5}]
    rows[3]['story']={'protect_action':True}
    text=json.dumps({'shots':rows})
    result=json.loads(ensure_burst(text,'high'))['shots']
    assert result[1]['sub_cuts']==rows[1]['sub_cuts']
    assert result[2].get('sub_cuts') and not result[3].get('sub_cuts')
    assert not result[0].get('sub_cuts') and not result[-1].get('sub_cuts')
    assert sum(edit_segment_frames(result))==360
    assert ensure_burst(json.dumps({'shots':result}),'high')==json.dumps({'shots':result})


def test_frame_durations_and_all_protected_actions_remain_usable():
    rows=[{'duration_frames':72,'prompt':'One continuous action','story':{'protect_action':True}} for _ in range(5)]
    text=json.dumps({'shots':rows})
    assert ensure_burst(text,'high')==text
    rows[2]={'duration_frames':72,'prompt':'Macro texture'}
    result=json.loads(ensure_burst(json.dumps({'shots':rows}),'high'))['shots']
    assert len(result[2]['sub_cuts'])==5 and result[2]['duration_frames']==72
