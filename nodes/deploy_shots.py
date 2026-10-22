from aiohttp import web
from comfy_api.latest import io
from server import PromptServer

from ..adapters.comfy_video import MajoorShotList
from ..core.deploy import deploy, list_recipes, load_recipe, pick_recipe
from ..core.errors import MajoorError


class MajoorDeployShots(io.ComfyNode):
    """Never executed: it only holds the settings of the Create shots button (web/majoor_deploy.js)."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        recipes = ["auto", *list_recipes()]
        return io.Schema(
            node_id="MajoorDeployShots",
            display_name="Deploy Shots",
            category="Majoor/VideoTools",
            description="Press Create shots: one block per shot (select, analysis, generation, apply, compare) is added to the graph from a recipe, chained, and sent to Shot Assemble.",
            inputs=[
                MajoorShotList.Input("shot_list", optional=True, tooltip="Scene Detect & Split or Create Timeline, run once so its shots are known. Without it, the first such node of the graph is used."),
                io.Combo.Input("recipe", options=recipes, default=recipes[0], tooltip="A workflow in the recipes folder of this pack: it holds one shot block, a Select Shot with the Set/Get nodes of its shot (SHOT_001_META...). Save your own workflow there to make another recipe. auto: the recipe of kind plan with the highest priority (Minimax H3 TimelineShot Creator) when the shots come with prompts (Create Timeline), a recipe of kind video for shots cut from a video (Scene Detect & Split). The created blocks read the shot list straight from the node that feeds this node's shot_list."),
                io.Int.Input("max_shots", default=0, min=0, max=500, tooltip="0 deploys every shot of the list."),
                io.Int.Input("columns", default=1, min=1, max=20, tooltip="Blocks per row on the canvas."),
                io.Boolean.Input("include_finale", default=True, tooltip="Also add Shot Assemble and Save Video when the graph has no Shot Assemble."),
                io.Boolean.Input("replace_existing", default=True, tooltip="A block already in the graph for one of the shots is replaced by the recipe's block. Off: stop instead."),
            ],
            outputs=[],
        )

    @classmethod
    def execute(cls, **kwargs) -> io.NodeOutput:
        return io.NodeOutput()


def register_routes() -> None:
    routes = PromptServer.instance.routes

    @routes.get("/majoor/recipes")
    async def recipes(request):
        return web.json_response({"recipes": list_recipes()})

    @routes.post("/majoor/deploy_shots")
    async def deploy_shots(request):
        try:
            body = await request.json()
            workflow, report = deploy(
                load_recipe(pick_recipe(str(body.get("recipe", "")), bool(body.get("has_plan", False)))),
                body["workflow"],
                [str(s) for s in body.get("shots", [])],
                anchor_id=body.get("anchor"),
                columns=int(body.get("columns", 1)),
                include_finale=bool(body.get("include_finale", True)),
                replace_existing=bool(body.get("replace_existing", True)),
            )
        except MajoorError as e:
            return web.json_response({"error": str(e)}, status=400)
        except (KeyError, TypeError, ValueError) as e:
            return web.json_response({"error": f"Invalid request: {e!r}"}, status=400)
        return web.json_response({"workflow": workflow, "report": report.to_dict()})
