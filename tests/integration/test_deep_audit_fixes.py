import sys
import subprocess
import time
import ast
from pathlib import Path

import numpy as np
import pytest

from majoor_videotools.core import music_fit
from majoor_videotools.adapters import ffmpeg
from majoor_videotools.core.errors import FFmpegError, PathError
from majoor_videotools.core.paths import ProjectStore


def test_short_music_loops_complete_bars_without_phase_drift(monkeypatch):
    rate = 8000
    monkeypatch.setattr(music_fit, 'analyze_rhythm', lambda samples, rate, bpm:{'bpm':120,'beats':np.arange(0,len(samples)/rate,.5),'timing_source':'user_grid'})
    monkeypatch.setattr(music_fit, '_downbeats', lambda samples, rate, beats, count:beats[::count])
    samples = np.linspace(.1,.4,round(11.4*rate),dtype=np.float32)[:,None]
    result, info = music_fit.fit_music(samples, rate, 30, bpm=120)
    resets = (np.flatnonzero(np.diff(result[:,0]) < -.15) + 1) / rate
    assert resets.tolist() == [10,20]
    assert info['looped'] and len(result) == 30*rate


def test_project_paths_cannot_escape_the_output_root(tmp_path):
    for project_id in ('../outside', str(tmp_path/'outside'), 'p_bad/../../outside'):
        with pytest.raises(PathError): ProjectStore(tmp_path/'projects', project_id)
    assert not (tmp_path/'outside').exists()


def test_music_save_node_checks_the_fork_id_before_writing(tmp_path):
    source = Path(__file__).resolve().parents[2]/'nodes/project_io.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MajoorSaveProjectMusic')
    method = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == 'execute')
    method.decorator_list = []
    method.returns = None
    scope = {'ProjectStore':ProjectStore,'projects_root':lambda:tmp_path/'projects','MUSIC_FILE':'music/retained.wav'}
    exec(compile(ast.Module(body=[method],type_ignores=[]),'music-save-boundary','exec'),scope)
    with pytest.raises(PathError):
        scope['execute'](None, None, None, '../outside')
    assert not (tmp_path/'outside').exists()


@pytest.mark.parametrize('cancel', [False, True])
def test_silent_ffmpeg_can_be_cancelled_or_timed_out(monkeypatch, cancel):
    popen = subprocess.Popen
    monkeypatch.setattr(ffmpeg, 'find_binary', lambda name:sys.executable)
    children = []
    def silent(*args, **kwargs):
        process = popen([sys.executable,'-c','import time;time.sleep(20)'], **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(ffmpeg.subprocess, 'Popen', silent)
    started = time.monotonic()
    with pytest.raises(FFmpegError, match='Cancelled' if cancel else 'time limit'):
        ffmpeg.run_ffmpeg([], is_cancelled=lambda:cancel, timeout=.15)
    assert time.monotonic() - started < 3
    assert children[0].poll() is not None
