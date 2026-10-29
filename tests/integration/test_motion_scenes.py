import json
import pytest
from majoor_videotools.core.motion_timing import shot_layers
from majoor_videotools.core.motion import parse_layers,needs_mask
from majoor_videotools.core.motion_scenes import readability,sound_events

TIMELINE=[{'id':'A','start':1,'duration':4}]
SCORE=[{'type':'vector','shape':'line','id':'rule','scene':'reveal','design':'tech','shot_id':'A','start':'10%','end':'30%','animation':'draw','sync':'onset'},
       {'type':'vector','shape':'dot','id':'point','scene':'reveal','shot_id':'A','after':'rule','delay':'5%','duration':'20%','motion_from':{'x':0},'motion_to':{'x':.4},'sfx':'ui_click_soft'},
       {'type':'text','id':'title','scene':'reveal','shot_id':'A','after':'point','duration':'25%','content':'SECATOR','design':'tech'}]


def resolve(rows=SCORE,duration=6,timeline=TIMELINE,hits=()):
    return shot_layers(json.dumps(rows),json.dumps(timeline),duration,30,hits)


def test_scene_dependencies_retime_with_shot_and_keep_order_independent():
    rows,_=resolve()
    assert rows[1]['start']==pytest.approx(2.4)
    assert rows[2]['start']==pytest.approx(3.2)
    reversed_rows,_=resolve(list(reversed(SCORE)))
    assert reversed_rows[0]['start']==rows[2]['start']
    shorter,_=resolve(duration=4,timeline=[{'id':'A','start':1,'duration':2}])
    assert shorter[1]['start']==pytest.approx(1.7)
    assert shorter[2]['start']==pytest.approx(2.1)


def test_scene_onset_moves_all_members_together_and_sound_follows():
    rows,alignment=resolve(hits=[1.5])
    assert alignment[0]['scene']=='reveal' and alignment[0]['matched']
    assert rows[0]['start']==1.5
    assert rows[1]['start']==pytest.approx(2.5)
    events=sound_events(SCORE,TIMELINE,6,30,[1.5])
    assert events==[(pytest.approx(rows[1]['start']),'ui_click_soft')]


def test_entered_dependency_overlaps_the_previous_visible_layer():
    score=[{**SCORE[0],'start':.1,'end':3.5,'in_time':.2}, {**SCORE[1],'after_phase':'entered','delay':0,'duration':.4}]
    rows,_=resolve(score)
    assert rows[1]['start']==pytest.approx(1.3)
    assert rows[1]['start']<rows[0]['end']


def test_vectors_and_style_do_not_request_a_mask_and_explicit_values_win():
    rows,_=resolve()
    layers=parse_layers(json.dumps(rows),6)
    assert not needs_mask(layers)
    assert layers[0]['thickness']==.002 and layers[2]['font']=='clean'
    assert layers[1]['motion_to']['x']==.4
    row={**SCORE[2],'font':'mono','color':'#123456','after':None,'start':0,'end':1}
    parsed=parse_layers(json.dumps(resolve([row])[0]),6)[0]
    assert parsed['font']=='mono' and parsed['color']=='#123456'


def test_graphic_handoff_preserves_position_and_velocity_at_cut():
    from majoor_videotools.core.motion_scenes import graphic_handoff
    pair=graphic_handoff(2.,.4,.5,velocity=(.2,0),at=(.5,.7))
    rows=parse_layers(json.dumps(pair),4)
    assert rows[0]['end']==rows[1]['start']==2
    assert rows[0]['motion_to']==rows[1]['motion_from']
    assert rows[0]['ease']==rows[1]['ease']=='linear'
    v0=(rows[0]['motion_to']['x']-rows[0]['motion_from']['x'])/rows[0]['in_time']
    v1=(rows[1]['motion_to']['x']-rows[1]['motion_from']['x'])/rows[1]['in_time']
    assert v0==pytest.approx(v1)


@pytest.mark.parametrize('rows',[
    [{**SCORE[0],'after':'missing'}],
    [{**SCORE[0],'after':'point'},SCORE[1]],
    [{**SCORE[0],'design':'madeup'}],
    [{**SCORE[0],'motion_to':{'scale':float('nan')}}],
])
def test_invalid_scene_contract_is_rejected(rows):
    with pytest.raises(ValueError):
        layers,_=resolve(rows)
        parse_layers(json.dumps(layers),6)


def test_readability_advisories_do_not_claim_semantic_approval():
    layers=parse_layers('[{"type":"text","content":"TOO SHORT","start":0,"end":0.1,"x":0.98,"y":0.99,"size":0.02}]',2)
    review=readability(layers,320,180,2)
    assert {w['kind'] for w in review['warnings']}=={'short_reading_window','small_text','possible_clipping'}


def test_assembler_mixes_scene_sound_only_when_enabled_and_respects_override(tmp_path):
    from majoor_videotools.core.template import create_template
    from majoor_videotools.core.assembler import AssemblyOptions,assemble_shots
    from majoor_videotools.core.media_probe import probe
    root=tmp_path/'projects'
    motion=[{'type':'vector','shape':'dot','start':.5,'end':1,'sfx':'ui_click_soft'}]
    shots=create_template(json.dumps({'shots':[{'id':'A','duration':2,'motion':motion}]}),root,fps=24,aspect_ratio='16:9',resolution=160,thumbnails=False,card_text=False)
    def assemble(**values):
        return assemble_shots(shots,root,AssemblyOptions(missing_shot_policy='use_original',audio_policy='mute',**values))
    assert not probe(assemble(auto_sfx=False).path).has_audio
    assert probe(assemble(auto_sfx=True).path).has_audio
    assert not probe(assemble(auto_sfx=True,motion_layers='[]').path).has_audio
