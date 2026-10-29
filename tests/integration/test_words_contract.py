import json
import shutil
import subprocess
from pathlib import Path
import pytest
from majoor_videotools.core.motion import parse_layers
from majoor_videotools.core.template import parse_plan
from majoor_videotools.core.motion_scenes import readability
from majoor_videotools.core.text_timing import animated_reading_budget


def test_planner_text_accepts_words_and_preserves_explicit_animation():
    for value,expected in [(None,'words'),('words','words'),('fade','fade'),('none','none')]:
        text={'content':'HELLO WORLD','accent_last':False}
        if value is not None:text['animation']=value
        result=parse_plan(json.dumps({'shots':[{'duration':2,'text':text}]}),24,'9:16',320)
        assert result.shots[0].fx['text']['animation']==expected
        assert result.shots[0].fx['text']['accent_last'] is False


def test_word_delay_and_exit_are_counted_before_reading_hold():
    content=' '.join('WORD'+str(i) for i in range(20))
    row=parse_layers(json.dumps([{'type':'text','content':content,'animation':'words','start':0,'end':6,'in_time':.5,'out':'fade','accent_last':False}]),6)[0]
    assert animated_reading_budget(content,'words',.5,'fade')==pytest.approx(7.71)
    assert {'layer':0,'kind':'short_reading_window'} in readability([row],1080,1920,6)['warnings']
    assert row['accent_last'] is False
    assert animated_reading_budget('ONE TWO','words',.25,'none',2)==pytest.approx(1.77)


def test_real_javascript_word_renderer_contract():
    node=shutil.which('node')
    if not node:pytest.skip('Node.js required for actual renderer contract')
    root=Path(__file__).resolve().parents[2]
    subprocess.run([node,str(root/'tests/js/word_renderer.cjs'),str(root/'web/hyperframes_layers.js')],check=True,capture_output=True,text=True)


def test_parsed_plan_text_keeps_its_shot_boundary_after_onset_alignment(monkeypatch):
    from types import SimpleNamespace
    from majoor_videotools.core.motion_timing import shot_layers
    root=Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root/'HyperKut Studio'))
    from backend.unified_motion import finishing_layers
    plan=parse_plan('{"shots":[{"id":"B","duration":1,"text":{"content":"HELLO WORLD","accent_last":false}}]}',24,'9:16',320)
    manifest={'shots':[{'shot_id':'B','plan':{'fx':plan.shots[0].fx}}]}
    rows=json.loads(finishing_layers(manifest,[SimpleNamespace(id='B',start=1,duration=1)],'[]'))
    assert rows[0]['animation']=='words' and rows[0]['shot_id']=='B'
    resolved,_=shot_layers(json.dumps(rows),'[{"id":"A","start":0,"duration":1},{"id":"B","start":1,"duration":1}]',2,24,[.9,1.04])
    assert 1<=resolved[0]['start']<2 and resolved[0]['end']<=2
    final=parse_layers(json.dumps(resolved),2)[0]
    assert final['animation']=='words' and final['accent_last'] is False
