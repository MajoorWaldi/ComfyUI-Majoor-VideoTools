import json

import pytest

from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.music_direction import parse_direction


def test_visual_direction_keeps_user_mood_and_visual_arrangement():
    data={'prompt':'delicate piano, airy pads, instrumental','energy':'calm','bpm':88,'variations':['minimal piano','organic plucks','ambient texture']}
    parsed=parse_direction(json.dumps(data),'sparse acoustic guitar',96)
    assert parsed['bpm']==96 and parsed['energy']=='calm'
    assert parsed['prompt'].startswith('sparse acoustic guitar')
    assert 'delicate piano' in parsed['prompt']
    assert 'variations' not in parsed


@pytest.mark.parametrize('text',['{}','bad','{"prompt":""}'])
def test_invalid_director_response_does_not_become_an_empty_music_prompt(text):
    with pytest.raises(MajoorError):parse_direction(text)


def test_key_description_is_normalized_without_losing_visual_arrangement():
    data={'prompt':'airy glassy plucks over a warm bass','key':'F Major (bright)','energy':'calm','variations':['piano','plucks','pads']}
    parsed=parse_direction(json.dumps(data),'no vocals')
    assert parsed['key']=='F major'
    assert 'airy glassy plucks' in parsed['prompt'] and parsed['prompt'].startswith('no vocals')


def test_actual_director_whitespace_and_capitalized_keys_are_not_lost():
    raw='```json\n'+json.dumps({'prompt ':'glassy textures','bpm':72,'energy':'calm','key':'Eb major','moments':[{'at':8,'Strength':.8}],'variations':['piano','plucks','pads']})+'\n```'
    parsed=parse_direction(raw)
    assert parsed['prompt']=='glassy textures'
    assert parsed['moments'][0]['strength']==.8
