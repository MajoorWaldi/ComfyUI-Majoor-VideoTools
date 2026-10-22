"""Load Video Advanced on real files: trim, crop, frame selection, the frame-by-frame reading of long clips, and its refusals. Needs ffmpeg."""
import subprocess
import tempfile
from pathlib import Path

import _boot
import folder_paths
import torch

import MVT.nodes.load_video_advanced as module
from MVT.core.errors import MajoorError

node = module.MajoorLoadVideoAdvanced
folder = Path(folder_paths.get_temp_directory()) / "majoor_check"
folder.mkdir(parents=True, exist_ok=True)


def make(name: str, *args: str) -> Path:
    path = folder / name
    if not path.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", *args, str(path)], check=True)
    return path


make("clip.mp4", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=24:d=3", "-f", "lavfi", "-i", "sine=f=440:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest")
make("upright.mp4", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=24:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p")
if not (folder / "rotated.mp4").exists():  # the same pixels with a display matrix of 90 degrees: shown as 240 x 320
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-display_rotation", "90", "-i", str(folder / "upright.mp4"), "-c", "copy", str(folder / "rotated.mp4")], check=True)
make("long.mp4", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=24:d=30", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p")
real = folder_paths.get_annotated_filepath
folder_paths.get_annotated_filepath = lambda name, *a, **k: str(folder / name) if name.endswith(".mp4") and "/" not in name and ".." not in name else real(name, *a, **k)


def run(file="clip.mp4", **kw):
    args = dict(file=file, start_time=0.0, duration=0.0, crop_x=0, crop_y=0, crop_width=0, crop_height=0, frames="") | kw
    video, images, indices = node.execute(**args).args
    return video, images, indices


def refuses(match, **kw):
    try:
        run(**kw)
    except MajoorError as e:
        assert match in str(e), (match, str(e))
        return
    raise AssertionError(f"not refused: {kw}")


def audio(video):
    return video.get_components().audio is not None


video, full, indices = run()
assert full.shape == (72, 240, 320, 3) and indices == list(range(72)) and audio(video)

# trim: counted in frames, to the frame
_, trimmed, _ = run(start_time=1.0, duration=0.5)
assert trimmed.shape[0] == 12 and torch.allclose(trimmed, full[24:36], atol=0.02)
_, late, _ = run(start_time=-1.0)
assert late.shape[0] == 24
# the start the widget writes is floored to the millisecond: 16/24 s is 0.666
assert torch.allclose(run(start_time=0.666, duration=0.5)[1][0], full[16], atol=0.02)
assert run(duration=10.0)[1].shape[0] == 72
refuses("no frame", start_time=5.0)

# crop (display coordinates, even sizes, cut at the edge of the frame)
assert run(crop_x=100, crop_y=50, crop_width=64, crop_height=48)[1].shape == (72, 48, 64, 3)
assert run(crop_x=10, crop_y=10, crop_width=63, crop_height=47)[1].shape == (72, 46, 62, 3)
assert run(crop_x=300, crop_width=64, crop_height=48)[1].shape == (72, 48, 20, 3)
assert run(file="rotated.mp4")[1].shape == (24, 320, 240, 3), "the frames come as they are shown"
assert run(file="rotated.mp4", crop_x=100, crop_y=200, crop_width=140, crop_height=100)[1].shape == (24, 100, 140, 3), "a crop is in the coordinates of the shown frame"

# selection
video, picked, indices = run(frames="0-9, ~5, -1")
assert picked.shape[0] == 16 and indices[-1] == 71 and not audio(video)
assert run(frames="~8")[2] == [0, 10, 20, 30, 41, 51, 61, 71]
assert audio(run(frames="0-71")[0]), "every frame in order keeps the video and its audio"
refuses("no frame", frames=",")
refuses("outside the video", frames="72")
refuses("Invalid video file", file="../../x.mp4")

# the frames read one by one are the frames of the full decode, with trim and crop
cases = [dict(frames="~8"), dict(frames="0, 10, -1"), dict(start_time=1.0, duration=1.0, frames="~4"), dict(start_time=-1.5, frames="0, ~3, -1"),
         dict(crop_x=20, crop_y=10, crop_width=100, crop_height=80, frames="~5"), dict(start_time=0.5, duration=1.5, crop_x=40, crop_y=30, crop_width=120, crop_height=90, frames="1, 20, 20, -2")]
for case in cases:
    module.SPARSE_BYTES = 10**12
    dense = run(**case)
    module.SPARSE_BYTES = 0
    sparse = run(**case)
    assert dense[1].shape == sparse[1].shape and torch.allclose(dense[1], sparse[1], atol=0.02) and dense[2] == sparse[2], case
module.SPARSE_BYTES = 512 * 1024**2

# a long clip is never held whole: 720 frames of 1080p would be 18 GB
import psutil  # noqa: E402

before = psutil.Process().memory_info().rss
_, kept, indices = run(file="long.mp4", frames="~8")
grown = (psutil.Process().memory_info().rss - before) / 1e9
assert kept.shape == (8, 1080, 1920, 3) and indices[-1] == 719 and grown < 2.0, grown
print("load video advanced ok (long clip: memory grew by %.2f GB)" % grown)
