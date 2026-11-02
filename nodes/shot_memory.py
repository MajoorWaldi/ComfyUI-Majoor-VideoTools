import numpy as np
import torch
from PIL import Image
from comfy_api.latest import io

from ..adapters.comfy_video import MajoorShotList, MajoorShotMetadata, projects_root, video_file
from ..core.memory import memory_key, recall, remember
from ..core.paths import ProjectStore


class MajoorSaveShotMemory(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorSaveShotMemory",
            display_name="Save Shot Memory",
            category="Majoor/VideoTools",
            description="Keep the sharpest frame of the take of a shot, filed under its character in the project, for Shot Memory to give to the next shots of that character. A shot without a character keeps nothing.",
            is_output_node=True,
            inputs=[MajoorShotList.Input("shot_list"), MajoorShotMetadata.Input("metadata"), io.Video.Input("video")],
            outputs=[],
        )

    @classmethod
    def execute(cls, shot_list, metadata, video) -> io.NodeOutput:
        shot = shot_list.get_shot(metadata.shot_id)
        character = memory_key((shot.plan or {}).get("cast"))
        if character:
            with video_file(video) as path:
                remember(ProjectStore(projects_root(shot_list), shot_list.project_id), character, shot.shot_id, path)
        return io.NodeOutput()


class MajoorShotMemory(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorShotMemory",
            display_name="Shot Memory",
            category="Majoor/VideoTools",
            description="The frame kept from the latest earlier shot of the same character, to give to H3 as one more picture, and the sentence that says what it is. "
                        "No earlier shot, no character, or reference pictures of your own (they already fix the look): has_memory is false and the sentence is empty.",
            inputs=[
                MajoorShotList.Input("shot_list"),
                MajoorShotMetadata.Input("metadata"),
                io.Image.Input("references", optional=True, tooltip="The reference pictures sent to H3. Connected, the memory is not used: your references fix the look."),
                io.Image.Input("plate", optional=True, tooltip="The empty place picture sent to H3 after the references, when there is one: the memory picture comes after it."),
            ],
            outputs=[
                io.Image.Output(display_name="image"),
                io.Boolean.Output(display_name="has_memory"),
                io.String.Output(display_name="prompt_line", tooltip="Add it to the prompt of H3: it names the memory picture by its number and keeps it to the identity."),
            ],
        )

    @classmethod
    def execute(cls, shot_list, metadata, references=None, plate=None) -> io.NodeOutput:
        shot = shot_list.get_shot(metadata.shot_id)
        path = None if references is not None else recall(ProjectStore(projects_root(shot_list), shot_list.project_id), shot_list, shot)
        if path is None:
            return io.NodeOutput(torch.zeros((1, 64, 64, 3)), False, "")
        image = torch.from_numpy(np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0)[None]
        number = 2 if plate is not None else 1
        line = f"<Picture {number}> only shows who this character is, from an earlier shot of this edit: keep its face, build and outfit. Its pose, framing, camera, movement and place do not carry over; this shot has its own."
        return io.NodeOutput(image, True, line, ui={"text": (f"memory from an earlier shot of {memory_key((shot.plan or {}).get('cast'))}",)})
