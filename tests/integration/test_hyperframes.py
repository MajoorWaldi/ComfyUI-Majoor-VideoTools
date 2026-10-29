import json
from pathlib import Path

import numpy as np
import pytest

from majoor_videotools.core.hyperframes import parse_direction, resolve_cues, write_composition
from majoor_videotools.core.media_probe import probe


def test_plain_direction_is_a_bounded_shorthand_not_executable_code():
    assert parse_direction('sobre #123456')['preset'] == 'minimal'
    assert parse_direction('très dynamique')['preset'] == 'energetic'
    assert parse_direction('editorial')['title'] == ''
    for value in ('{"preset":"unknown"}', '{"accent":"red;url(x)"}', '{"script":"alert(1)"}', '{"intensity":NaN}'):
        with pytest.raises(ValueError):
            parse_direction(value)


def test_shot_cues_use_final_timing_and_reject_spill_or_unknown_shots():
    timeline = json.dumps([{'id':'A','start':2,'duration':3}])
    cue = resolve_cues('[{"shot_id":"A","text":"REVEAL"}]', timeline, 8, 24)[0]
    assert cue['start'] == 2 and cue['end'] == 4.4
    for value in ('[{"shot_id":"B","text":"x"}]', '[{"shot_id":"A","start":0,"text":"x"}]', '[{"start":7,"end":9,"text":"x"}]'):
        with pytest.raises(ValueError):
            resolve_cues(value,timeline,8,24)
    with pytest.raises(ValueError,match='overlap'):
        resolve_cues('[{"text":"a","start":0,"end":2},{"text":"b","start":1,"end":3}]','[]',8,24)


def test_composition_escapes_titles_and_keeps_original_media_muted_for_remux(tmp_path,fixtures):
    source=fixtures['gen']
    info=probe(source,with_packets=False)
    gsap=tmp_path/'gsap.js';gsap.write_text('// test')
    caption='</script><script>alert(1)</script>'
    cues=resolve_cues(json.dumps([{'text':caption,'start':0,'end':1}]),'[]',float(info.duration),24)
    project=tmp_path/'project'
    write_composition(project,source,info,parse_direction('minimal'),cues,{'bands':[],'hits':[],'audio':False},gsap)
    scene=(project/'compositions/motion.html').read_text()
    assert '&lt;' in scene and '\\u003c/script' in scene
    assert '<script>alert(1)</script>' not in scene
    assert '__DURATION__' not in scene and '__CONFIG__' not in scene
    assert 'muted playsinline' in (project/'index.html').read_text()


def test_absent_audio_produces_no_false_audio_hits(fixtures):
    from majoor_videotools.core.hyperframes import analyze_audio
    info=probe(fixtures['gen'],with_packets=False)
    info.has_audio=False
    assert analyze_audio(fixtures['gen'],info)=={'bands':[],'hits':[],'audio':False}


def test_optional_runtime_error_is_actionable(monkeypatch,tmp_path):
    from majoor_videotools.core.hyperframes import runtime_paths
    monkeypatch.setenv('MAJOOR_HYPERFRAMES_RUNTIME',str(tmp_path))
    with pytest.raises(RuntimeError,match='optional'):
        runtime_paths()
