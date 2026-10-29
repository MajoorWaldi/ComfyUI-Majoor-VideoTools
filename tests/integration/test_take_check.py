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


def test_a_file_that_cannot_be_read_is_reported(tmp_path):
    (tmp_path / "broken.mp4").write_bytes(b"not a video")
    assert check_take(tmp_path / "broken.mp4") == (False, "no frame could be read")
