import json
import wave
from pathlib import Path
import numpy as np
import pytest
from majoor_videotools.core.tone_sfx import tone_library, tone_library_status, _read_tone_library, design_cues, KINDS
from majoor_videotools.core.sfx import render_track, RATE
from majoor_videotools.core.errors import MajoorError

def test_installed_palette_has_30_distinct_finite_sounds():
    bank,key=tone_library()
    if not bank:pytest.skip('Optional Tone.js runtime not installed')
    assert set(bank)==set(KINDS) and key.startswith('tone-')
    fingerprints=set()
    for kind,x in bank.items():
        assert np.isfinite(x).all() and 0.05<len(x)/RATE<2
        assert float(np.max(np.abs(x)))==pytest.approx(1)
        fingerprints.add(x[:5000].tobytes())
    assert len(fingerprints)==30

def test_missing_runtime_keeps_legacy_fallback(monkeypatch,tmp_path):
    monkeypatch.setenv('MAJOOR_TONE_RUNTIME',str(tmp_path))
    assert tone_library()==({},'procedural-v1')

def test_palette_rejects_incompatible_manifest(monkeypatch,tmp_path):
    monkeypatch.setenv('MAJOOR_TONE_RUNTIME',str(tmp_path))
    (tmp_path/'bank').mkdir();(tmp_path/'bank/tone.json').write_text('{"engine":"unknown"}')
    with pytest.raises(MajoorError,match='palette'):_read_tone_library()
    assert tone_library_status()==({}, 'procedural-v1', 'optional:tone:unavailable')
    assert tone_library()==({}, 'procedural-v1')

def test_lead_is_cropped_at_zero_instead_of_moved_late():
    sample=np.arange(1000,dtype=np.float32)/1000
    track=render_track([(.26,'whoosh')],1,{'whoosh':sample},generated={'whoosh'})
    # lead .275: the first 720 samples must be trimmed, not replayed at t=0.
    assert abs(track[0,0])>.05
    assert not np.any(track[281:])

def test_sparse_edits_stay_sparse_and_user_cues_are_preserved():
    assert len(design_cues([(2,'hit'),(5,'hit')],12))==2
    assert design_cues([(2,'hit')],3,{'hit'})==[(2,'hit')]
    score=design_cues([(3,'impact'),(4,'hit'),(8,'impact')],10)
    assert score.count((2.94,'riser'))==1
    assert not any(at==7.94 and kind=='riser' for at,kind in score)

def test_dense_overlap_bus_remains_finite_and_below_full_scale():
    bank,_=tone_library()
    if not bank:pytest.skip('Optional Tone.js runtime not installed')
    x=render_track([(1,kind) for kind in KINDS],3,bank,generated=set(bank))
    assert x.shape==(144000,2) and np.isfinite(x).all()
    assert np.max(np.abs(x))<1 and np.max(np.abs(x))>.05


def test_directional_stereo_survives_rendering():
    bank,_=tone_library()
    if 'stereo_whoosh_lr' not in bank:pytest.skip('Expanded optional bank not installed')
    for name,forward in [('stereo_whoosh_lr',True),('stereo_whoosh_rl',False)]:
        x=bank[name]
        assert x.ndim==2 and x.shape[1]==2
        early=np.sum(x[:len(x)//3]**2,axis=0)
        late=np.sum(x[len(x)*2//3:]**2,axis=0)
        assert (early[0]>early[1]) == forward
        assert (late[1]>late[0]) == forward
        mixed=render_track([(1,name)],2,bank,generated=set(bank))
        assert not np.allclose(mixed[:,0],mixed[:,1])

def test_selection_is_conservative_and_legacy_banks_still_work():
    base=[(1,'whoosh'),(3,'whoosh'),(4,'hit'),(5,'hit'),(6,'hit')]
    selected=design_cues(base,10)
    assert len(selected)==len(base)
    assert selected[0][1]=='stereo_whoosh_lr' and selected[1][1]=='stereo_whoosh_rl'
    assert not any(kind.startswith(('logo_','notification_')) for _,kind in selected)
    legacy=set(KINDS[:16])
    assert all(kind in legacy for _,kind in design_cues(base,10,available=legacy))

def test_stereo_user_wav_keeps_its_channels(tmp_path):
    from majoor_videotools.core.sfx_library import load_library
    frames=np.zeros((2400,2),dtype='<i2');frames[:,0]=2000
    with wave.open(str(tmp_path/'stereo.wav'),'wb') as out:
        out.setnchannels(2);out.setsampwidth(2);out.setframerate(24000);out.writeframes(frames.tobytes())
    (tmp_path/'manifest.json').write_text(json.dumps({'stereo_sweep':{'file':'stereo.wav','license':'local test','source':'synthetic'}}))
    bank,_=load_library(str(tmp_path))
    assert bank['stereo_sweep'].shape==(4800,2)
    assert np.any(bank['stereo_sweep'][:,0]) and not np.any(bank['stereo_sweep'][:,1])


@pytest.mark.parametrize('manifest', ['{', '[]', 'null', '{"engine":"tone.js","version":"15.1.22","entries":null}'])
def test_unusable_optional_bank_falls_back_without_reading_invalid_assets(monkeypatch,tmp_path,manifest):
    monkeypatch.setenv('MAJOOR_TONE_RUNTIME',str(tmp_path))
    (tmp_path/'bank').mkdir()
    (tmp_path/'bank/tone.json').write_text(manifest)
    assert tone_library_status()==({}, 'procedural-v1', 'optional:tone:unavailable')
    assert tone_library()==({}, 'procedural-v1')


def test_absent_bank_returns_warning_for_the_studio(monkeypatch,tmp_path):
    monkeypatch.setenv('MAJOOR_TONE_RUNTIME',str(tmp_path))
    assert tone_library_status()==({}, 'procedural-v1', 'optional:tone:missing')
