import json
import subprocess
from fractions import Fraction

from majoor_videotools.core.dialogue import lines_of_shot
from majoor_videotools.core.media_probe import probe
from majoor_videotools.core.project import fork_shot_list, load_shot_list
from majoor_videotools.core.scene_detection import detect_scenes
from majoor_videotools.core.revisions import apply_revision, make_metadata


def test_decimal_shot_header_assigns_only_its_dialogue():
    assert lines_of_shot('SHOT_002 · 3.00-6.00s · 3.00s · 72 frames', '0-2 s: FIRST\n3-5 s: SECOND') == '0.00-2.00 s: SECOND'


def test_project_json_survives_temporary_windows_reader(tmp_path):
    import os,threading,pytest
    from majoor_videotools.core.paths import ProjectStore
    if os.name!='nt':pytest.skip('Windows file-sharing semantics')
    store=ProjectStore(tmp_path,'p_12345678')
    path=store.write_json('manifest.json',{'revision':1})
    reader=path.open('rb')
    timer=threading.Timer(.12,reader.close)
    timer.start()
    try:store.write_json('manifest.json',{'revision':2})
    finally:
        timer.join()
        reader.close()
    assert store.read_json('manifest.json')=={'revision':2}


def test_audio_stream_before_video_is_probed(tmp_path):
    path=tmp_path/'audio-first.mp4'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=440:duration=1','-f','lavfi','-i','color=c=red:s=64x64:r=24:d=1','-map','0:a','-map','1:v','-c:a','aac','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True)
    info=probe(path)
    assert info.frame_count==24 and info.fps==Fraction(24)


def test_tasks_fork_the_initial_collection_without_reusing_each_others_takes(fixtures,tmp_path):
    original=detect_scenes(fixtures['one'],tmp_path,'manual',.5,1,thumbnails=False)
    first=fork_shot_list(tmp_path,original,'p_11111111')
    shot=first.shots[0]
    modified=apply_revision(first,tmp_path,make_metadata(first,shot,shot.active),fixtures['gen'])
    second=fork_shot_list(tmp_path,original,'p_22222222')
    assert modified.shots[0].active_revision_id!='original'
    assert second.shots[0].active_revision_id=='original'
    assert load_shot_list(tmp_path,original.project_id).shots[0].active_revision_id=='original'
    assert (tmp_path/second.project_id/second.source.uri).is_file()


def test_spectral_analysis_is_chunked_and_tempo_does_not_use_quadratic_correlation(monkeypatch):
    import numpy as np
    from majoor_videotools.core.beats import onset_envelope, estimate_bpm
    def forbidden(*a,**k):raise AssertionError('unbounded allocation or direct correlation')
    monkeypatch.setattr(np,'stack',forbidden)
    monkeypatch.setattr(np,'correlate',forbidden)
    samples=np.zeros(44100*12,dtype=np.float32)
    samples[::22050]=1
    env,hop=onset_envelope(samples,44100)
    assert len(env)>1000 and 110<estimate_bpm(env,hop)<130
