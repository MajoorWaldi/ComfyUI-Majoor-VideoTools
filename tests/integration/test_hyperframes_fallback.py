import logging

import pytest

from majoor_videotools.core import hyperframes, motion
from majoor_videotools.core.errors import FFmpegError, MajoorError, MediaError


def _raise(error):
    def render(*args, **kwargs):
        raise error

    return render


def test_motion_graphics_runtime_failure_passes_through_and_reports_cause(tmp_path, monkeypatch, caplog):
    source = tmp_path / 'source.mp4'
    output = tmp_path / 'motion.mp4'
    source.write_bytes(b'original video')
    monkeypatch.setattr(hyperframes, 'render_hyperframes', _raise(RuntimeError('CLI render failed')))

    with caplog.at_level(logging.WARNING):
        report = motion.render_motion(source, [], output)

    assert output.read_bytes() == source.read_bytes()
    assert report['status'] == 'fallback' and report['original_retained']
    assert report['warnings'] == ['optional:hyperframes:unavailable']
    detail = report['warning_details'][0]['message']
    assert 'RuntimeError: CLI render failed' in detail
    assert 'RuntimeError: CLI render failed' in caplog.text


def test_motion_graphics_cancellation_is_never_passed_through(tmp_path, monkeypatch):
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'original video')
    monkeypatch.setattr(hyperframes, 'render_hyperframes', _raise(RuntimeError('render stopped')))

    with pytest.raises(InterruptedError, match='cancelled'):
        motion.render_motion(source, [], tmp_path / 'motion.mp4', is_cancelled=lambda: True)


@pytest.mark.parametrize('error', [
    ValueError('bad direction'),
    MajoorError('invalid layers'),
    MediaError('invalid video'),
])
def test_invalid_inputs_are_not_converted_to_optional_fallback(tmp_path, monkeypatch, error):
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'original video')
    monkeypatch.setattr(hyperframes, 'render_hyperframes', _raise(error))

    with pytest.raises(type(error), match=str(error)):
        motion.render_motion(source, [], tmp_path / 'motion.mp4')


@pytest.mark.parametrize('error', [
    InterruptedError('stopped'),
    FFmpegError('Cancelled'),
])
def test_interrupted_render_is_never_passed_through(tmp_path, monkeypatch, error):
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'original video')
    monkeypatch.setattr(hyperframes, 'render_hyperframes', _raise(error))

    with pytest.raises(InterruptedError):
        motion.render_motion(source, [], tmp_path / 'motion.mp4')
