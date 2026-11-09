from aiohttp import web
from comfy_api.latest import io
from server import PromptServer

from ..core.generators import describe, generation_frames_for, generation_seconds_for, list_generators, load_generator

VIDEO = list_generators("video")


class MajoorGeneratorSelect(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorGeneratorSelect",
            display_name="Generator Select",
            category="Majoor/VideoTools",
            description="The video model of the graph: one choice that every shot block reads. Branches of the shot block are switched on by Generator Is, and Generator Limits gives the length to ask for and what the model accepts.",
            inputs=[io.Combo.Input("generator", options=VIDEO, default="minimax_h3", tooltip="A file of the generators folder of this pack: add a file there to offer another model.")],
            outputs=[io.String.Output(display_name="generator")],
        )

    @classmethod
    def execute(cls, generator) -> io.NodeOutput:
        gen = load_generator(generator)
        return io.NodeOutput(gen.id, ui={"text": (f"{gen.title} · {gen.source} · {gen.cost}",)})


class MajoorGeneratorIs(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorGeneratorIs",
            display_name="Generator Is",
            category="Majoor/VideoTools",
            description="True when the selected generator is the one named here. Wired to the switch of a branch, so that only the chosen model runs (and only it is paid for).",
            inputs=[
                io.String.Input("generator", force_input=True, tooltip="The generator of Generator Select."),
                io.Combo.Input("is", options=VIDEO, default="minimax_h3", tooltip="The model of this branch."),
            ],
            outputs=[io.Boolean.Output(display_name="selected")],
        )

    @classmethod
    def execute(cls, generator, **kwargs) -> io.NodeOutput:
        return io.NodeOutput(generator == kwargs["is"])


class MajoorGeneratorLimits(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorGeneratorLimits",
            display_name="Generator Limits",
            category="Majoor/VideoTools",
            description="What to ask the selected generator for a shot of target_frames: the frames, and the seconds for a model that works in whole seconds (0 for a frame-grid model), plus how many pictures, videos and audios it takes (-1: unknown).",
            inputs=[
                io.String.Input("generator", force_input=True, tooltip="The generator of Generator Select."),
                io.Int.Input("target_frames", default=72, min=1, max=100000, tooltip="The length of the shot in the edit."),
                io.Float.Input("fps", default=24.0, min=1.0, max=240.0, step=0.001, tooltip="The fps of the plan."),
            ],
            outputs=[
                io.Int.Output(display_name="generation_frames"),
                io.Float.Output(display_name="generation_seconds"),
                io.Int.Output(display_name="max_images"),
                io.Int.Output(display_name="max_videos"),
                io.Int.Output(display_name="max_audios"),
            ],
        )

    @classmethod
    def execute(cls, generator, target_frames, fps) -> io.NodeOutput:
        gen = load_generator(generator)
        seconds = generation_seconds_for(generator, target_frames, fps)
        caps = [-1 if gen.limit(k) is None else gen.limit(k) for k in ("images", "videos", "audios")]
        return io.NodeOutput(generation_frames_for(generator, target_frames, fps), 0.0 if seconds is None else seconds, *caps)


def register_routes() -> None:
    routes = PromptServer.instance.routes

    @routes.get("/majoor/generators")
    async def generators(request):
        kind = request.query.get("kind") or None
        return web.json_response({"generators": [describe(g) for g in list_generators(kind)]})
