import os
import tempfile
from pathlib import Path

from comfy_api.latest import io

from ..adapters.comfy_video import MajoorShotList, projects_root
from ..core.paths import ProjectStore

LYRICS_FILE = "music/lyrics.json"


class MajoorSaveProjectLyrics(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorSaveProjectLyrics",
            display_name="Save Project Lyrics",
            category="Majoor/VideoTools",
            description="Keep the words of the music (with their times) as a file of the project, so that the edit can write them on the screen later, whatever the transcriber does or holds in memory.",
            is_output_node=True,
            inputs=[MajoorShotList.Input("shot_list"), io.String.Input("words_json", default="", force_input=True, tooltip="Words with times, [{word, start, end}]. Empty: nothing is kept."),
                    io.String.Input("fork_project_id", default="", optional=True, tooltip="The project of Save Project Info when it makes its own copy: the words go to that one.")],
            outputs=[io.String.Output(display_name="saved_words")],
        )

    @classmethod
    def execute(cls, shot_list, words_json, fork_project_id="") -> io.NodeOutput:
        path = ProjectStore(projects_root(shot_list), fork_project_id.strip() or shot_list.project_id).resolve(LYRICS_FILE)
        if not words_json.strip():
            path.unlink(missing_ok=True)
            return io.NodeOutput(words_json, ui={"text": ("no words",)})
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(words_json)
            os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)
        return io.NodeOutput(words_json, ui={"text": (str(path),)})
