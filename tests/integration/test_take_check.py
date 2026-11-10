import subprocess

import pytest

from majoor_videotools.core.take_check import check_take


def _clip(tmp_path, name, source, vf="null"):
    path = tmp_path / f"{name}.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", source, "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("takes")
    return {
        "black": _clip(d, "black", "color=c=black:s=192x256:r=24:d=2"),
        "white": _clip(d, "white", "color=c=white:s=192x256:r=24:d=2"),
        "noise": _clip(d, "noise", "color=c=gray:s=192x256:r=24:d=2", "geq=random(1)*255:128:128"),
        "picture": _clip(d, "picture", "testsrc2=s=192x256:r=24:d=2"),
        "dark": _clip(d, "dark", "testsrc2=s=192x256:r=24:d=2", "eq=brightness=-0.75"),  # a silhouette shot: dark, but a picture
        "still": _clip(d, "still", "testsrc2=s=192x256:r=1:d=2", "fps=24"),  # a macro that does not move
        "busy": _clip(d, "busy", "testsrc2=s=192x256:r=24:d=2", "noise=alls=40:allf=t"),  # a neon arcade: a lot of detail, still a picture
    }


@pytest.mark.parametrize("name, ok, word", [("black", False, "black"), ("white", False, "white"), ("noise", False, "only noise"), ("picture", True, "fine"), ("dark", True, "fine"), ("still", True, "fine"), ("busy", True, "fine")])
def test_only_the_clear_failures_are_caught(clips, name, ok, word):
    found, report = check_take(clips[name])
    assert found is ok and word in report


@pytest.mark.parametrize("asked, ok, word", [
    (dict(aspect="3:4", resolution="", seconds=2.0), True, "192x256"),  # 192x256 is 3:4, two seconds
    (dict(aspect="9:16"), False, "9:16 was asked"),
    (dict(resolution="720p"), False, "720p was asked"),
    (dict(seconds=5.0), False, "5 s was asked"),
    (dict(aspect="3:4", seconds=2.1), True, "192x256"),  # a few frames off the length is not a fault
    (dict(aspect="wide"), False, "not a ratio"),
    (dict(), True, "fine"),  # nothing asked: only the look is checked
])
def test_the_file_is_measured_against_what_was_asked(clips, asked, ok, word):
    found, report = check_take(clips["picture"], **asked)
    assert found is ok and word in report


def test_a_take_off_its_settings_is_refused_before_its_pixels_are_looked_at(clips):
    assert check_take(clips["black"], aspect="9:16") == (False, "the shape is 192x256 (0.75), 9:16 was asked (0.56)")


def test_a_file_that_cannot_be_read_is_reported(tmp_path):
    (tmp_path / "broken.mp4").write_bytes(b"not a video")
    assert check_take(tmp_path / "broken.mp4") == (False, "no frame could be read")


def test_a_take_that_cannot_be_measured_is_not_made_again(tmp_path, monkeypatch):
    from majoor_videotools.core import take_check
    monkeypatch.setattr(take_check, "probe_take", lambda _p: {})  # no ffprobe, or a file it cannot read
    ok, said = take_check.check_settings(tmp_path / "x.mp4", "9:16", "720p", 5)
    assert ok and "not checked" in said  # a retry would be paid and measured no better


def test_an_edit_is_checked_on_its_resolution_only(tmp_path, monkeypatch):
    from majoor_videotools.core import take_check
    monkeypatch.setattr(take_check, "probe_take", lambda _p: {"width": 1280, "height": 720, "fps": 24.0, "seconds": 8.0})
    assert not take_check.check_settings(tmp_path / "x.mp4", "9:16", "720p", 5)[0]  # a new take in the wrong shape and length: made again
    assert take_check.check_settings(tmp_path / "x.mp4", "9:16", "720p", 5, task="edit")[0]  # an edit keeps the shape and length of its source
    assert not take_check.check_settings(tmp_path / "x.mp4", "9:16", "1080p", 5, task="edit")[0]
