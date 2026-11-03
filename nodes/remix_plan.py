from comfy_api.latest import io

from ..adapters.comfy_video import MajoorShotList
from ..core.errors import MajoorError
from ..core.remix_plan import apply_remix_plan, parse_remix_plan, plan_summary


class MajoorRemixPlan(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorRemixPlan",
            display_name="Remix Plan",
            category="Majoor/VideoTools",
            description="Lay the answer of the remix_planner skill on the shots found in the source: the story line of each shot, who it shows (a reference picture or a character), "
                        "its place, and whether it is generated, kept as in the source or replaced by a title card. The cuts and durations of the source never change. "
                        "Not connected, or an answer that is not JSON: the shot list passes unchanged.",
            inputs=[
                MajoorShotList.Input("shot_list"),
                io.String.Input("plan_json", force_input=True, optional=True, tooltip="The answer of the LLM to the remix_planner skill."),
                io.Boolean.Input("cast", default=True, optional=True, tooltip="Write who each shot shows, for Shot Memory and the shot prompt."),
                io.Boolean.Input("places", default=False, optional=True, tooltip="Write the place of each shot: Select Shot gives it as location, for the empty place picture."),
                io.Boolean.Input("keep_sources", default=True, optional=True, tooltip="Let the plan keep a shot as in the source or turn it into a title card instead of generating it."),
                io.Int.Input("pictures", default=5, min=0, max=5, optional=True, tooltip="How many reference pictures the shots get: a person the plan gives a picture that does not exist is described by its look instead."),
            ],
            outputs=[MajoorShotList.Output(display_name="shot_list"),
                     io.String.Output(display_name="plan_text", tooltip="The story and what each shot becomes, in words.")],
        )

    @classmethod
    def execute(cls, shot_list, plan_json=None, cast=True, places=False, keep_sources=True, pictures=5) -> io.NodeOutput:
        if not plan_json or not plan_json.strip():
            return io.NodeOutput(shot_list, "", ui={"text": ("no plan: the shots stay as detected",)})
        try:
            plan = parse_remix_plan(plan_json, pictures)
        except MajoorError as error:  # a remix never stops on its planner: the shots keep the analysis of the shot graph
            return io.NodeOutput(shot_list, "", ui={"text": (f"plan not used: {error}",)})
        planned = apply_remix_plan(shot_list, plan, cast=cast, places=places, keep_sources=keep_sources)
        kept = sum(1 for s in planned.shots if ((s.plan or {}).get("render_source") or {}).get("kind") not in (None, "generated"))
        named = sum(1 for s in shot_list.shots if s.shot_id.upper() in plan["shots"])
        return io.NodeOutput(planned, plan_summary(plan, planned), ui={"text": (f"{named} shots planned, {kept} not generated, {len(plan['characters'])} people",)})
