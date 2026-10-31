from comfy_api.latest import io

from ..adapters.comfy_video import MajoorShotList
from ..core.casting import apply_casting, parse_casting


class MajoorApplyCasting(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorApplyCasting",
            display_name="Apply Casting",
            category="Majoor/VideoTools",
            description="Give each shot a character of the casting: its look, place, shot size and performance go into the plan, so Select Shot and Edit Skills carry the same identity from take to take.",
            inputs=[
                MajoorShotList.Input("shot_list"),
                io.String.Input("casting_json", force_input=True, optional=True, tooltip="The answer of the LLM to the casting_planner skill. Not connected: the shot list passes unchanged."),
            ],
            outputs=[MajoorShotList.Output(display_name="shot_list")],
        )

    @classmethod
    def execute(cls, shot_list, casting_json=None) -> io.NodeOutput:
        if casting_json is None:
            return io.NodeOutput(shot_list)
        casting = parse_casting(casting_json)
        return io.NodeOutput(apply_casting(shot_list, casting), ui={"text": (", ".join(f"{c['name']} {c['start']:g}-{c['end']:g} s" for c in casting["characters"]),)})
