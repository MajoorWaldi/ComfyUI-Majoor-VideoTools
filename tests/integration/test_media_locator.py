from pathlib import Path

import pytest

from majoor_videotools.core.errors import PathError
from majoor_videotools.core.media_locator import project_media_location


@pytest.mark.parametrize("root", ["MajoorVideoTools", "_hyperkut_workspaces/" + "a" * 32 + "/projects"])
def test_legacy_and_isolated_media_use_actual_output_root(tmp_path, root):
    output = tmp_path / "output"
    storage = output / root
    project = "p_12345678"
    location = project_media_location(storage, project, output, "generated/take.mp4")
    assert location == root + "/" + project + "/generated/take.mp4"
    assert str(tmp_path) not in location


@pytest.mark.parametrize("relative", ["../secret", "other/../secret", "/absolute", "C:/private", "%2e%2e/secret", "a\\..\\b"])
def test_rejects_unsafe_media_paths(tmp_path, relative):
    with pytest.raises(PathError):
        project_media_location(tmp_path / "output/projects", "p_12345678", tmp_path / "output", relative)


def test_external_storage_requires_artifact_transfer(tmp_path):
    with pytest.raises(PathError, match="remote artifact transfer"):
        project_media_location(tmp_path / "outside", "p_12345678", tmp_path / "output")


def test_symlink_cannot_escape_project(tmp_path):
    output = tmp_path / "output"
    project = output / "projects/p_12345678"
    project.mkdir(parents=True)
    outside = tmp_path / "private"
    outside.mkdir()
    try:
        (project / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires privileges on this Windows installation")
    with pytest.raises(PathError):
        project_media_location(output / "projects", "p_12345678", output, "link/secret.mp4")
