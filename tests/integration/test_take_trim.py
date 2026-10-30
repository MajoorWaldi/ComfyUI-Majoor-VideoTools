import dataclasses
import json
import subprocess
from fractions import Fraction

import numpy as np
import pytest

from majoor_videotools.core.assembler import AssemblyOptions, _fx_segments, _source_offset, assemble_shots
from majoor_videotools.core.models import Revision, ShotList
from majoor_videotools.core.paths import ProjectStore
from majoor_videotools.core.template import create_template
from majoor_videotools.core.revisions import apply_revision, make_metadata
from majoor_videotools.core.media_probe import probe
from majoor_videotools.core.errors import AssemblyError


def test_slip_changes_decoded_picture_and_take_audio_without_changing_duration(tmp_path):
    source=tmp_path/'four_seconds.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=red:s=128x128:r=24:d=4',
                    '-f','lavfi','-i',r'aevalsrc=sin(2*PI*if(lt(t\,2)\,440\,880)*t):s=48000:d=4',
                    '-vf',"drawbox=x=0:y=0:w=iw:h=ih:c=blue:t=fill:enable='gte(t,2)'",'-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True)
    root=tmp_path/'projects'
    sl=create_template(json.dumps({'shots':[{'duration':1,'prompt':'A color'}]}),root,fps=24,aspect_ratio='1:1',resolution=128,thumbnails=False)
    shot=sl.shots[0]
    sl=apply_revision(sl,root,make_metadata(sl,shot,shot.active),source)
    original=assemble_shots(sl,root,AssemblyOptions(audio_policy='shot_audio',effects=False))
    shot=sl.shots[0]
    shifted=dataclasses.replace(shot.active,source_start_seconds=2)
    shot=dataclasses.replace(shot,revisions=tuple(shifted if r.revision_id==shifted.revision_id else r for r in shot.revisions))
    sl=dataclasses.replace(sl,shots=(shot,))
    assert ShotList.from_dict(sl.to_dict()).shots[0].active.source_start_seconds==2
    result=assemble_shots(sl,root,AssemblyOptions(audio_policy='shot_audio',effects=False))
    assert result.path!=original.path and not result.reused
    assert probe(result.path,with_packets=False).frame_count==24
    def rgb(path):
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-frames:v','1','-vf','scale=1:1','-pix_fmt','rgb24','-f','rawvideo','-'])
        return list(raw[:3])
    assert rgb(original.path)[0]>200 and rgb(result.path)[2]>200
    audio=np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-i',str(result.path),'-vn','-ac','1','-ar','8000','-f','f32le','-']),dtype='<f4')
    frequency=np.argmax(abs(np.fft.rfft(audio)))*8000/len(audio)
    assert abs(frequency-880)<5


def test_subcuts_and_self_composites_shift_together(tmp_path):
    sl=create_template(json.dumps({'shots':[{'duration':2,'prompt':'Detail'}]}),tmp_path/'projects',fps=24,aspect_ratio='1:1',resolution=128,thumbnails=False)
    store=ProjectStore(tmp_path/'projects',sl.project_id)
    fx={'sub_cuts':[{'frames':24,'start':0},{'frames':24,'start':2,'speed':2}]}
    args=(sl.shots[0],'take_001',tmp_path/'video.mp4',Fraction(5),fx,48,Fraction(24),128,128,store)
    original=_fx_segments(*args)
    shifted=_fx_segments(*args,source_offset=.5)
    assert [s.frames for s in shifted]==[24,24]
    assert [float(s.seek[1]) if s.seek else 0 for s in shifted]==[.5,2.5]
    assert [float(s.seek[1]) if s.seek else 0 for s in original]==[0,2]


@pytest.mark.parametrize('start',[-1,float('nan'),float('inf'),5])
def test_invalid_source_offsets_are_rejected(start):
    with pytest.raises(AssemblyError):
        _source_offset(Revision('take_001','video.mp4',5,'ready',source_start_seconds=start),Fraction(5))


@pytest.mark.parametrize("fps", [Fraction(24), Fraction(25), Fraction(30000, 1001)])
def test_subcuts_cannot_read_after_slipped_take_end(tmp_path, fps):
    sl = create_template(json.dumps({"shots": [{"duration": 3, "prompt": "Detail"}]}), tmp_path / "projects", fps=24, aspect_ratio="1:1", resolution=128, thumbnails=False)
    store = ProjectStore(tmp_path / "projects", sl.project_id)
    frames = round(3 * fps)
    fx = {"sub_cuts": [{"frames": round(fps)}, {"frames": round(fps)}, {"frames": round(fps)}],
          "overlay": [{"source": "self", "offset": 3, "opacity": .5, "blend": "screen", "scale": 1, "position": "center"}]}
    segments = _fx_segments(sl.shots[0], "take_001", tmp_path / "video.mp4", Fraction(5), fx, frames, fps, 128, 128, store, source_offset=2)
    for segment in segments:
        duration = float(segment.seconds)
        assert float(segment.seek[1]) + duration <= 5 + 1e-6
        for layer in segment.layers:
            assert float(layer.seek[1]) + duration <= 5 + 1e-6
    assert sum(segment.frames for segment in segments) == frames


def test_subcut_overrun_requires_explicit_padding(tmp_path):
    sl = create_template(json.dumps({"shots": [{"duration": 4, "prompt": "Detail"}]}), tmp_path / "projects", fps=24, aspect_ratio="1:1", resolution=128, thumbnails=False)
    store = ProjectStore(tmp_path / "projects", sl.project_id)
    args = (sl.shots[0], "take_001", tmp_path / "video.mp4", Fraction(5), {"speed": 1}, 96, Fraction(24), 128, 128, store)
    with pytest.raises(AssemblyError, match="only 3"):
        _fx_segments(*args, source_offset=2)
    warnings = []
    result = _fx_segments(*args, source_offset=2, allow_padding=True, warnings=warnings)
    assert result[0].seek == ["-ss", "2.000000"]
    assert any("padded" in warning for warning in warnings)
