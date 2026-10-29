import json
import wave

import numpy as np
import pytest

from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.sfx_library import load_library


def test_local_cue_resamples_and_hashes_content(tmp_path):
    wav=tmp_path/'hit.wav'
    def write(value):
        with wave.open(str(wav),'wb') as out:
            out.setnchannels(1);out.setsampwidth(2);out.setframerate(24000)
            out.writeframes(np.full(2400,value,dtype='<i2').tobytes())
    write(1000)
    (tmp_path/'manifest.json').write_text(json.dumps({'hit':{'file':'hit.wav','license':'User supplied private test','source':'local recording'}}))
    sounds,key=load_library(str(tmp_path))
    assert len(sounds['hit'])==4800
    write(2000)
    assert load_library(str(tmp_path))[1]!=key


def test_local_cue_rejects_traversal_and_missing_provenance(tmp_path):
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'hit':{'file':'../escape.wav','license':'CC0','source':'local'}}))
    with pytest.raises(MajoorError,match='inside'):load_library(str(tmp_path))
    manifest.write_text(json.dumps({'hit':{'file':'hit.wav'}}))
    with pytest.raises(MajoorError,match='required'):load_library(str(tmp_path))
