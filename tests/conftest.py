"""Core tests run without ComfyUI: the repo is exposed as the package 'majoor_videotools' without executing its __init__."""
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pkg = types.ModuleType("majoor_videotools")
pkg.__path__ = [str(ROOT)]
sys.modules.setdefault("majoor_videotools", pkg)


def _ffmpeg(args: list[str], out: Path) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args, str(out)], check=True)
    return out


@pytest.fixture(scope="session")
def fixtures(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("fixtures")
    size = "320x240"
    # three visually unrelated 2 s scenes at 24 fps with a continuous tone
    scenes = [
        f"color=c=red:s={size}:r=24:d=2",
        f"testsrc2=s={size}:r=24:d=2",
        f"smptebars=s={size}:r=24:d=2",
    ]
    inputs = [a for s in scenes for a in ("-f", "lavfi", "-i", s)]
    hard = _ffmpeg(
        [*inputs, "-f", "lavfi", "-i", "sine=f=440:d=6:r=48000", "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a",
         "-c:v", "libx264", "-g", "12", "-pix_fmt", "yuv420p", "-c:a", "aac"],
        d / "hard_cuts_3.mp4",
    )
    one = _ffmpeg(["-f", "lavfi", "-i", f"testsrc2=s={size}:r=24:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p"], d / "one_shot.mp4")
    gen = _ffmpeg(
        ["-f", "lavfi", "-i", "testsrc=s=160x120:r=30:d=5", "-f", "lavfi", "-i", "sine=f=880:d=5", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"],
        d / "generated_5s.mp4",
    )
    gen_short = _ffmpeg(["-f", "lavfi", "-i", "smptebars=s=640x360:r=25:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p"], d / "generated_1s.mp4")
    # 30 fps whose second frame is only a few ms after the first (seen in real phone/editor exports)
    jitter = _ffmpeg(
        ["-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=3", "-vf", "setpts='if(eq(N,0),0,(N-0.9)/(30*TB))'", "-fps_mode", "passthrough",
         "-c:v", "libx264", "-pix_fmt", "yuv420p"],
        d / "jitter_start.mp4",
    )
    return {"jitter": jitter, "hard": hard, "one": one, "gen": gen, "gen_short": gen_short}
