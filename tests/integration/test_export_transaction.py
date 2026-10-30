import json
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from conftest import ROOT
from majoor_videotools.core.errors import AssemblyError
from majoor_videotools.core.export_transaction import durable_audio, export_lock
from majoor_videotools.core.paths import ProjectStore


def test_cancelled_lock_does_not_enter_transaction(tmp_path):
    store = ProjectStore(tmp_path, "p_12345678")
    with pytest.raises(AssemblyError, match="Cancelled"):
        with export_lock(store, "same-key", lambda: True):
            pytest.fail("Cancelled export acquired transaction")


def test_durable_audio_survives_temporary_input_deletion(tmp_path):
    store = ProjectStore(tmp_path / "projects", "p_12345678")
    original = tmp_path / "temporary.wav"
    with wave.open(str(original), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\0\0" * 8000)
    metadata = durable_audio(store, original)
    original.unlink()
    assert store.resolve(metadata["media_ref"]).is_file()
    assert metadata["duration_seconds"] == 1
    assert metadata["sample_rate"] == 8000
    assert "temporary" not in json.dumps(metadata)
    assert metadata["media_ref"].startswith("sources/audio/")
    restarted = ProjectStore(tmp_path / "projects", "p_12345678")
    assert restarted.read_json("sources/audio/index.json")["assets"][metadata["asset_id"]] == metadata


WORKER = r"""
import json, sys, types, time
from pathlib import Path
pkg = types.ModuleType('majoor_videotools'); pkg.__path__ = [sys.argv[1]]
sys.modules['majoor_videotools'] = pkg
from majoor_videotools.core.project import load_shot_list
from majoor_videotools.core import assembler
from majoor_videotools.core.errors import FFmpegError
root, project_id, marker = Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
real = assembler.run_ffmpeg
started = None
mode = sys.argv[5] if len(sys.argv) > 5 else ''
def counted(*args, **kwargs):
    global started
    started = time.monotonic()
    with marker.open('ab') as stream: stream.write(b'encode\n')
    if mode == 'cancel':
        args = (['-re', *args[0]], *args[1:])
    if mode.startswith('parallel-'):
        marker.with_name(mode + '.active').touch()
        deadline = time.monotonic() + 10
        while len(list(marker.parent.glob('parallel-*.active'))) < 2:
            if time.monotonic() >= deadline:
                raise RuntimeError('Independent export keys did not enter encoding concurrently')
            time.sleep(.02)
    return real(*args, **kwargs)
assembler.run_ffmpeg = counted
try:
    result = assembler.assemble_shots(load_shot_list(root, project_id), root,
        assembler.AssemblyOptions(audio_policy='mute', effects=False,
            output_name=mode if mode.startswith('parallel-') else 'majoor_edit'),
        is_cancelled=lambda: mode == 'cancel' and started is not None and time.monotonic() - started > .5)
except FFmpegError as error:
    if mode != 'cancel' or 'Cancelled' not in str(error):
        raise
    print(json.dumps({'cancelled': True}))
else:
    print(json.dumps({'path': str(result.path), 'reused': result.reused}))
"""


def test_two_processes_encode_same_export_once(fixtures, tmp_path):
    from majoor_videotools.core.scene_detection import detect_scenes

    root = tmp_path / "projects"
    project = detect_scenes(fixtures["one"], root, "manual", .5, 1, thumbnails=False)
    marker = tmp_path / "encodes.log"
    args = [sys.executable, "-c", WORKER, str(ROOT), str(root), project.project_id, str(marker)]
    processes = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    outputs = []
    try:
        for process in processes:
            out, err = process.communicate(timeout=120)
            assert process.returncode == 0, err
            outputs.append(json.loads(out.strip().splitlines()[-1]))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
    assert marker.read_bytes() == b"encode\n"
    assert outputs[0]["path"] == outputs[1]["path"]
    assert sorted(row["reused"] for row in outputs) == [False, True]
    assert not list((root / project.project_id / "exports").glob("*.partial*"))



def test_audio_cancellation_is_checked_before_subprocess(tmp_path):
    from majoor_videotools.core.audio_quality import _run_audio

    with pytest.raises(InterruptedError, match="cancelled"):
        _run_audio(["this-program-must-never-start"], timeout=1, is_cancelled=lambda: True)


def test_audio_cancel_kills_running_process(tmp_path):
    import time
    from majoor_videotools.core.audio_quality import _run_audio

    started = time.monotonic()
    with pytest.raises(InterruptedError, match="cancelled"):
        _run_audio([sys.executable, "-c", "import time; time.sleep(60)"], timeout=5,
                   is_cancelled=lambda: time.monotonic() - started > .2)


def test_interrupted_encoder_releases_lock_and_next_process_recovers(fixtures, tmp_path):
    import time
    from majoor_videotools.core.scene_detection import detect_scenes
    from majoor_videotools.core.media_probe import probe

    root = tmp_path / "projects"
    project = detect_scenes(fixtures["one"], root, "manual", .5, 1, thumbnails=False)
    marker = tmp_path / "encodes.log"
    args = [sys.executable, "-c", WORKER, str(ROOT), str(root), project.project_id, str(marker)]
    first = subprocess.Popen([*args, "cancel"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    second = None
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline and first.poll() is None:
            time.sleep(.02)
        assert marker.exists(), "First encoder did not start"
        second = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = first.communicate(timeout=30)
        assert first.returncode == 0, err
        assert json.loads(out.strip().splitlines()[-1]) == {"cancelled": True}
        out, err = second.communicate(timeout=30)
        assert second.returncode == 0, err
        result = json.loads(out.strip().splitlines()[-1])
        assert not result["reused"]
        assert probe(Path(result["path"])).frame_count == 72
        assert marker.read_bytes() == b"encode\nencode\n"
        assert not list((root / project.project_id / "exports").glob("*.partial*"))
    finally:
        for process in (first, second):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()


def test_lock_timeout_and_cancellation_during_contention(tmp_path):
    from filelock import FileLock
    from majoor_videotools.core.fingerprints import json_fingerprint

    store = ProjectStore(tmp_path, "p_12345678")
    path = store.resolve("cache/export_locks/" + json_fingerprint("busy") + ".lock")
    path.parent.mkdir(parents=True)
    with FileLock(str(path)):
        with pytest.raises(AssemblyError, match="Timed out"):
            with export_lock(store, "busy", timeout=.05):
                pytest.fail("A held lock was acquired")
        calls = 0
        def cancelled():
            nonlocal calls
            calls += 1
            return calls >= 2
        with pytest.raises(AssemblyError, match="Cancelled while waiting"):
            with export_lock(store, "busy", cancelled):
                pytest.fail("Cancelled contender was admitted")


def test_distinct_exports_really_encode_in_parallel(fixtures, tmp_path):
    from majoor_videotools.core.scene_detection import detect_scenes

    root = tmp_path / "projects"
    project = detect_scenes(fixtures["one"], root, "manual", .5, 1, thumbnails=False)
    marker = tmp_path / "encodes.log"
    args = [sys.executable, "-c", WORKER, str(ROOT), str(root), project.project_id, str(marker)]
    processes = [subprocess.Popen([*args, mode], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for mode in ("parallel-a", "parallel-b")]
    results = []
    try:
        for process in processes:
            out, err = process.communicate(timeout=30)
            assert process.returncode == 0, err
            results.append(json.loads(out.strip().splitlines()[-1]))
        assert results[0]["path"] != results[1]["path"]
        assert all(not result["reused"] for result in results)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
