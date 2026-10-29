import json

from majoor_videotools.core.timeline_sources import fit_duration,merge_plans,plan_to_dict
from majoor_videotools.core.template import parse_plan


def test_requested_duration_preserves_total_frames_after_rounding():
    text=json.dumps({'shots':[{'duration':s} for s in [2,3,2,2,9]]})
    plan=parse_plan(fit_duration(text,20,24),24,'1:1',128)
    assert sum(s.frames for s in plan.shots)==480


def test_music_merge_and_plan_roundtrip_keep_local_render_source():
    source={'kind':'graphic','text':'HELLO','color':'#000000'}
    text=json.dumps({'shots':[{'id':'TITLE','duration':1,'render_source':source}]})
    plan=parse_plan(text,24,'1:1',128)
    assert plan_to_dict(plan)['shots'][0]['render_source']==source
    merged,_=merge_plans(json.dumps({'shots':[{'id':'TITLE','duration':2}]}),text,24,'1:1',128)
    assert merged['shots'][0]['render_source']==source
    assert merged['shots'][0]['duration_frames']==48
