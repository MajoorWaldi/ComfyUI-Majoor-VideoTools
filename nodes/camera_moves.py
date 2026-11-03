from comfy_api.latest import io

from ..adapters.comfy_video import MajoorShotList
from ..core.camera_moves import add_camera_moves


class MajoorCameraMoves(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorCameraMoves",
            display_name="Camera Moves",
            category="Majoor/VideoTools",
            description="Give every shot a camera move: a shot whose prompt names none, or the same one as the shot before, gets the next of twelve moves (push-in, orbit, whip pan, crane...). "
                        "A brief that asks for a fixed camera is left alone.",
            inputs=[
                MajoorShotList.Input("shot_list"),
                io.String.Input("brief", default="", optional=True, force_input=True, tooltip="The brief of the edit: a fixed or static camera in it turns the node off."),
                io.Int.Input("seed", default=0, min=0, max=0x7fffffff, optional=True, tooltip="Where in the list of moves to start: another number gives other moves."),
                io.Boolean.Input("enabled", default=True, optional=True, tooltip="Off: the shot list passes unchanged."),
                io.Float.Input("min_seconds", default=0.0, min=0.0, max=60.0, step=0.1, optional=True, tooltip="A shot shorter than this gets no move: too short for a move to read, it keeps the movement of its source. 0: every shot."),
            ],
            outputs=[MajoorShotList.Output(display_name="shot_list")],
        )

    @classmethod
    def execute(cls, shot_list, brief="", seed=0, enabled=True, min_seconds=0.0) -> io.NodeOutput:
        return io.NodeOutput(add_camera_moves(shot_list, brief, seed, min_seconds) if enabled else shot_list)
