import json
import os
import tempfile
from pathlib import Path

from comfy_api.latest import io

from ..adapters.comfy_video import MajoorShotList, projects_root
import numpy as np
import torch

from ..core.beats import read_wav, write_wav
from ..core.paths import ProjectStore, sanitize_name
from ..core.project import fork_shot_list, load_shot_list
from .preview import shots_payload


class MajoorSaveProjectInfo(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorSaveProjectInfo",
            display_name="Save Project Info",
            category="Majoor/VideoTools",
            description="Write the project of a shot list (its id and, for every shot, its start, duration, prompt, thumbnail and takes) to output/MajoorVideoTools/_jobs/<name>.json, "
                        "so that a program that drives ComfyUI through its API can read it: the outputs of the API only carry files.",
            is_output_node=True,
            inputs=[MajoorShotList.Input("shot_list"), io.String.Input("name", default="job", tooltip="Name of the file (letters, digits, - and _)."),
                    io.String.Input('fork_project_id', default='', optional=True, tooltip='Optional independent project, p_ followed by 8–32 hexadecimal digits.')],
            outputs=[],
        )

    @classmethod
    def execute(cls, shot_list, name, fork_project_id='') -> io.NodeOutput:
        if fork_project_id:
            shot_list = fork_shot_list(projects_root(), shot_list, fork_project_id)
        path = projects_root() / "_jobs" / f"{sanitize_name(name)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        # The index lives beside projects, so use a temporary file in the same folder.
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'project_id': shot_list.project_id, **shots_payload(shot_list)}, stream)
            os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)
        return io.NodeOutput(ui={"text": (str(path),)})


class MajoorLoadShotList(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorLoadShotList",
            display_name="Load Shot List",
            category="Majoor/VideoTools",
            description="Read the shot list of a project from its manifest, with the takes that Apply Shot Metadata registered in earlier runs: the assembly can be its own run.",
            inputs=[io.String.Input("project_id", default="", tooltip="p_ followed by hexadecimal digits: the project of Create Timeline or Scene Detect (Save Project Info writes it).")],
            outputs=[MajoorShotList.Output(display_name="shot_list")],
        )

    @classmethod
    def fingerprint_inputs(cls, project_id):
        """The manifest changes between runs (Apply Shot Metadata registers takes in it) while the input does not: without this ComfyUI would hand back the shot list of an earlier run."""
        return ProjectStore(projects_root(), project_id.strip()).resolve("manifest.json").stat().st_mtime_ns

    @classmethod
    def execute(cls, project_id) -> io.NodeOutput:
        return io.NodeOutput(load_shot_list(projects_root(), project_id.strip()))


MUSIC_FILE = "music/retained.wav"


class MajoorSaveProjectMusic(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorSaveProjectMusic",
            display_name="Save Project Music",
            category="Majoor/VideoTools",
            description="Keep the music of the edit as a file of the project, so that the edit can be made again from the takes and this file, whatever the music models do or hold in memory.",
            is_output_node=True,
            inputs=[MajoorShotList.Input("shot_list"), io.Audio.Input("music"),
                    io.String.Input("fork_project_id", default="", optional=True, tooltip="The project of Save Project Info when it makes its own copy: the music goes to that one.")],
            outputs=[],
        )

    @classmethod
    def execute(cls, shot_list, music, fork_project_id="") -> io.NodeOutput:
        path = ProjectStore(projects_root(), fork_project_id.strip() or shot_list.project_id).resolve(MUSIC_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        samples = music["waveform"][0].cpu().numpy().T  # [channels, T] -> [T, channels]
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        os.close(fd)
        try:
            write_wav(Path(tmp), samples, int(music["sample_rate"]))
            os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)
        return io.NodeOutput(ui={"text": (str(path),)})


class MajoorLoadProjectMusic(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorLoadProjectMusic",
            display_name="Load Project Music",
            category="Majoor/VideoTools",
            description="The music that Save Project Music kept for the project: the edit starts from this file, not from the music models.",
            inputs=[io.String.Input("project_id", default="", tooltip="p_ followed by hexadecimal digits.")],
            outputs=[io.Audio.Output(display_name="music")],
        )

    @classmethod
    def fingerprint_inputs(cls, project_id):
        return ProjectStore(projects_root(), project_id.strip()).resolve(MUSIC_FILE).stat().st_mtime_ns

    @classmethod
    def execute(cls, project_id) -> io.NodeOutput:
        path = ProjectStore(projects_root(), project_id.strip()).resolve(MUSIC_FILE)
        if not path.is_file():
            raise FileNotFoundError(f"Project {project_id} has no kept music ({path}): run the first step of the job again")
        samples, rate = read_wav(path)
        return io.NodeOutput({"waveform": torch.from_numpy(np.ascontiguousarray(samples.T)).unsqueeze(0), "sample_rate": rate})
