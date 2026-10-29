import importlib
import shutil
import sys
import types

import pytest


@pytest.fixture
def comfy_video(tmp_path, monkeypatch):
    """adapters.comfy_video with ComfyUI's folder_paths and comfy_api replaced by minimal stubs."""
    dirs = {name: tmp_path / name for name in ("output", "input", "temp")}
    for d in dirs.values():
        d.mkdir()
    folder_paths = types.ModuleType("folder_paths")
    folder_paths.get_output_directory = lambda: str(dirs["output"])
    folder_paths.get_input_directory = lambda: str(dirs["input"])
    folder_paths.get_temp_directory = lambda: str(dirs["temp"])
    io = types.SimpleNamespace(Custom=lambda name: name)
    api = types.ModuleType("comfy_api")
    latest = types.ModuleType("comfy_api.latest")
    latest.io = io
    latest.AudioInput = dict
    latest.VideoFromComponents = object
    latest.VideoFromFile = object
    monkeypatch.setitem(sys.modules, "folder_paths", folder_paths)
    monkeypatch.setitem(sys.modules, "comfy_api", api)
    monkeypatch.setitem(sys.modules, "comfy_api.latest", latest)
    monkeypatch.delitem(sys.modules, "majoor_videotools.adapters.comfy_video", raising=False)
    module = importlib.import_module("majoor_videotools.adapters.comfy_video")
    return module, dirs


class FileVideo:
    def __init__(self, path):
        self.path = str(path)

    def get_stream_source(self):
        return self.path

    def get_active_trim_window(self):
        return (0.0, 0.0)

    def get_dimensions(self):
        from majoor_videotools.core.media_probe import probe

        info = probe(self.path, with_packets=False)
        return (info.width, info.height)


class CroppedVideo(FileVideo):
    """A file with a crop: the same file, a smaller picture (as VideoFromFile.as_cropped makes it)."""

    def get_dimensions(self):
        return (64, 48)

    def save_to(self, path):
        shutil.copy(self.path, path)


def test_files_in_output_are_referenced_in_place(comfy_video, fixtures):
    module, dirs = comfy_video
    (dirs["output"] / "sub").mkdir()
    shutil.copy(fixtures["gen"], dirs["output"] / "sub" / "a.mp4")
    ref = module.preview_ref(FileVideo(dirs["output"] / "sub" / "a.mp4"))
    assert (ref["file"], ref["folder"], ref["kind"]) == ("a.mp4", "sub", "output")
    assert (ref["width"], ref["height"]) == (160, 120) and abs(ref["duration"] - 5) < 0.1


def test_files_elsewhere_are_copied_to_temp_once(comfy_video, fixtures):
    module, dirs = comfy_video
    ref = module.preview_ref(FileVideo(fixtures["gen"]))
    assert (ref["folder"], ref["kind"]) == ("majoor_compare", "temp")
    copied = dirs["temp"] / "majoor_compare" / ref["file"]
    assert copied.is_file() and copied.stat().st_size == fixtures["gen"].stat().st_size
    assert module.preview_ref(FileVideo(fixtures["gen"])) == ref
    assert not list((dirs["temp"] / "majoor_compare").glob("*.partial"))


def test_input_folder_files_are_referenced_in_place(comfy_video, fixtures):
    module, dirs = comfy_video
    shutil.copy(fixtures["gen"], dirs["input"] / "in.mp4")
    ref = module.preview_ref(FileVideo(dirs["input"] / "in.mp4"))
    assert (ref["file"], ref["folder"], ref["kind"]) == ("in.mp4", "", "input")


def test_a_cropped_video_is_rendered_not_used_in_place(comfy_video, fixtures):
    module, dirs = comfy_video
    with module.video_file(FileVideo(fixtures["gen"])) as path:
        assert str(path) == str(fixtures["gen"])
    with module.video_file(CroppedVideo(fixtures["gen"])) as path:
        assert str(path) != str(fixtures["gen"]) and path.is_file()  # the crop is in the copy ComfyUI saves, not in the file
    assert not list((dirs["output"] / "MajoorVideoTools" / "_tmp").glob("*.mp4"))
