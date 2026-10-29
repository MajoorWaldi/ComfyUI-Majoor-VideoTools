import sys
from types import SimpleNamespace
import pytest
from majoor_videotools.core.hyperframes import _render_command, validate_silent_render
from majoor_videotools.core.media_probe import probe


def test_finished_artifact_can_recover_only_a_hanging_shutdown(tmp_path, fixtures):
    info = probe(fixtures['gen'], with_packets=False)
    command = [sys.executable, '-u', '-c', 'import time; print(\'{"message":"artifact validated"}\',flush=True); print("Render complete",flush=True); time.sleep(60)']
    checked = []
    def validate():
        validate_silent_render(fixtures['gen'], info)
        checked.append(True)
    assert _render_command(command, tmp_path, tmp_path/'render.log', None, None, timeout=15, completed=validate)
    assert checked == [True]


def test_no_completion_marker_does_not_turn_a_timeout_into_success(tmp_path):
    command = [sys.executable, '-u', '-c', 'import time; time.sleep(60)']
    called = []
    with pytest.raises(TimeoutError):
        _render_command(command,tmp_path,tmp_path/'render.log',None,None,timeout=.1,completed=lambda:called.append(True))
    assert not called


def test_real_process_failure_stays_failure(tmp_path):
    with pytest.raises(RuntimeError,match='failed'):
        _render_command([sys.executable,'-c','raise SystemExit(7)'],tmp_path,tmp_path/'render.log',None,None)


def test_wrong_artifact_is_rejected_even_when_it_decodes(fixtures):
    info = probe(fixtures['gen'],with_packets=False)
    wrong = SimpleNamespace(display_size=(999,999),fps=info.fps,duration=info.duration)
    with pytest.raises(RuntimeError,match='validation'):
        validate_silent_render(fixtures['gen'],wrong)
