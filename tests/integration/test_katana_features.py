import json
import numpy as np
import pytest
from pathlib import Path
from majoor_videotools.core.plate_quality import parse_plate_assessment
from majoor_videotools.core.energy import Event,summarize_energy,compare_energy
from majoor_videotools.core.template import parse_plan,create_template
from majoor_videotools.core.render_source import render_planned_source
from majoor_videotools.core.errors import MajoorError


@pytest.mark.parametrize('raw,status',[
    ('bad JSON','uncertain'),('{"status":"person","reason":"reflection"}','person'),
    ('```json\n{"status":"clear","reason":"empty room"}\n```','clear'),
    ('{"status":"clear"}','uncertain'),('{"status":"unknown","reason":"dark"}','uncertain'),
])
def test_plate_decisions_are_conservative(raw,status):
    assert parse_plate_assessment(raw)['status']==status


def test_energy_compares_densities_and_preserves_unknown_zero_ratios():
    a=summarize_energy([Event('flash',10,3,1),Event('shake',30,10,1)],[24],2)
    b=summarize_energy([Event('flash',10,3,1),Event('flash',50,3,1)], [24,48],4)
    assert a['flash_rate']==b['flash_rate']==.5
    assert a['shake_rate']==.5
    assert compare_energy(a,b)['ratios']['flash_rate']==1
    assert compare_energy(b,a)['ratios']['shake_rate'] is None
    assert compare_energy(None,b)['status']=='unmeasured'


def test_energy_zero_duration_is_not_a_real_measurement():
    with pytest.raises(ValueError):summarize_energy([],[],0)


@pytest.mark.parametrize('mode',['text','music'])
def test_plate_guard_is_on_both_reference_and_prompt_paths(mode):
    root=Path(__file__).resolve().parents[2]
    prompt=json.loads((root/f'HyperKut Studio/workflows/{mode}/shot.api.json').read_text())
    assert any(n['class_type']=='MajoorCheckPlate' for n in prompt.values())
    check=next(k for k,n in prompt.items() if n['class_type']=='MajoorCheckPlate')
    safe=next(n for n in prompt.values() if n['class_type']=='ComfySwitchNode' and n['inputs'].get('on_true')==[check,0])  # the plate that H3 receives passes the check, and only when places are on
    enabled=prompt[str(safe['inputs']['switch'][0])]
    assert enabled['class_type']=='PrimitiveBoolean' and enabled['_meta']['title'].startswith('PLACES')


@pytest.mark.parametrize('mode',['text','music','remix'])
def test_energy_analysis_is_in_final_prompt_without_regenerating_shots(mode):
    root=Path(__file__).resolve().parents[2]
    prompt=json.loads((root/f'HyperKut Studio/workflows/{mode}/final.api.json').read_text())
    reports=[n for n in prompt.values() if n['class_type']=='MajoorEnergyReport']
    assert len(reports)==1 and reports[0]['inputs']['shot_list']==['p3',0]
    assert not any(n['class_type']=='MajoorApplyShotMetadata' for n in prompt.values())


def test_graphic_source_has_zero_h3_budget_and_exact_frames(tmp_path):
    text=json.dumps({'fps':24,'width':128,'height':128,'shots':[{'id':'TITLE','duration':1,'render_source':{'kind':'graphic','text':'HELLO','color':'#204060'}}]})
    collection=create_template(text,tmp_path,fps=24,aspect_ratio='1:1',resolution=128,profile='minimax_h3',thumbnails=False)
    shot=collection.shots[0]
    assert shot.plan['generation_frames']==0
    from majoor_videotools.core.paths import ProjectStore
    path=render_planned_source(ProjectStore(tmp_path,collection.project_id),shot,collection.source.fps,128,128)
    from majoor_videotools.core.media_probe import probe
    assert probe(path).frame_count==24


def test_unknown_render_source_is_rejected_before_gpu():
    with pytest.raises(MajoorError):
        parse_plan(json.dumps({'shots':[{'duration':1,'render_source':{'kind':'python','code':'bad'}}]}),24,'1:1',128)


def test_api_templates_do_not_link_missing_nodes():
    root=Path(__file__).parents[2]/'HyperKut Studio/workflows'
    for path in root.glob('*/*.api.json'):
        graph=json.loads(path.read_text(encoding='utf-8'))
        for key,node in graph.items():
            for value in node['inputs'].values():
                if isinstance(value,list) and len(value)==2 and isinstance(value[1],int):
                    assert str(value[0]) in graph,(str(path),key,value)


def test_new_report_directories_are_written_atomically(tmp_path):
    from majoor_videotools.core.paths import ProjectStore
    store=ProjectStore(tmp_path,'p_12345678')
    store.dir.mkdir(parents=True,exist_ok=True)
    for path in ('cache/energy/new.json','logs/plate_checks/SHOT_001.json'):
        store.write_json(path,{'status':'clear'})
        assert store.read_json(path)=={'status':'clear'}
