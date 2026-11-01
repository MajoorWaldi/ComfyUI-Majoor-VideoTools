from comfy_api.latest import io

from ..adapters.comfy_video import MajoorShotList
from ..core.errors import MajoorError
import json

from ..core.casting import apply_casting, parse_casting, parse_references, sheet_prompt


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
                io.String.Input("references_json", default="", optional=True, force_input=True, tooltip='Reference pictures by character: {"ghoul": "ghoul.png", "witch": ["witch_a.png", "witch_b.png"]}. Each shot of a character carries its pictures in plan.cast.references, so every shot uses the same identity.'),
                io.String.Input("shot_energy_json", default="", optional=True, force_input=True, tooltip='Optional {"SHOT_001": 0.8, ...} (0 to 1): with shot_sizes "auto", the Creative Director goes closer on energetic shots.'),
            ],
            outputs=[MajoorShotList.Output(display_name="shot_list"),
                     io.String.Output(display_name="character_sheets_json", tooltip="{character id: prompt} to generate the reference picture of each character once.")],
        )

    @classmethod
    def execute(cls, shot_list, casting_json=None, references_json="", shot_energy_json="") -> io.NodeOutput:
        if casting_json is None:
            return io.NodeOutput(shot_list, "")
        casting = parse_casting(casting_json)
        references = parse_references(references_json, casting)
        try:
            energies = json.loads(shot_energy_json) if shot_energy_json and shot_energy_json.strip() else None
        except ValueError as error:
            raise MajoorError("shot_energy_json is not valid JSON") from error
        if energies is not None and (not isinstance(energies, dict) or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in energies.values())):
            raise MajoorError('shot_energy_json must be {"shot id": number}')
        sheets = {c["id"]: sheet_prompt(casting, c["id"]) for c in casting["characters"]}
        return io.NodeOutput(apply_casting(shot_list, casting, references, energies), json.dumps(sheets), ui={"text": (", ".join(f"{c['name']} {c['start']:g}-{c['end']:g} s" for c in casting["characters"]),)})
