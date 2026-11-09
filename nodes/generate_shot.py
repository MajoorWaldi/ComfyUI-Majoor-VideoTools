from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder, is_link

from server import PromptServer

from ..core.api_request import ASPECTS, RESOLUTIONS, build_request
from ..core.cost_guard import DEFAULT_BUDGET_SECONDS, Ledger
from ..core.pricing import badge_of, evaluate
from ..core.errors import MajoorError
from ..core.generators import list_generators, load_generator

API = [g for g in list_generators("video") if load_generator(g).source == "api"]
N_IMAGES = 9
LEDGER = Ledger()


def api_budget(dynprompt) -> tuple[int, float]:
    """MAX API SECONDS and MAX API USD of the Generator Select of the graph being run (the defaults when the graph has none or they are wired to something)."""
    for node_id in dynprompt.all_node_ids():
        node = dynprompt.get_node(node_id)
        if node.get("class_type") == "MajoorGeneratorSelect":
            seconds, usd = node.get("inputs", {}).get("max_api_seconds", DEFAULT_BUDGET_SECONDS), node.get("inputs", {}).get("max_api_usd", 0.0)
            return (DEFAULT_BUDGET_SECONDS if is_link(seconds) else int(seconds)), (0.0 if is_link(usd) else float(usd))
    return DEFAULT_BUDGET_SECONDS, 0.0


class MajoorGenerateShot(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorGenerateShot",
            display_name="Generate Shot (API)",
            category="Majoor/VideoTools",
            description="Makes the take of a shot with an API video model (Seedance, Wan, LTX...) chosen by the generator of Generator Select, from the same settings whatever the model: "
                        "the node it needs is created when the graph runs, so only the chosen model is called and paid for. "
                        "Pictures a model does not take are left out; a model that needs a picture or video of the shot and gets none stops with a clear message.",
            inputs=[
                io.String.Input("generator", force_input=True, tooltip="The generator of Generator Select (an API model; the local H3 has its own branch)."),
                io.String.Input("prompt", force_input=True, tooltip="The prompt of the shot."),
                io.Float.Input("seconds", default=5.0, min=1.0, max=60.0, step=0.01, force_input=True, tooltip="generation_seconds of Select Shot or Generator Limits: the model is asked for these whole seconds."),
                io.Combo.Input("aspect_ratio", options=list(ASPECTS), default="16:9", tooltip="LTX makes 16:9 and 9:16 only."),
                io.Combo.Input("resolution", options=list(RESOLUTIONS), default="720p", tooltip="Higher costs more. LTX makes 720p and 1080p only."),
                io.Boolean.Input("generate_audio", default=True, tooltip="The model makes its own sound for the take."),
                io.Int.Input("seed", default=0, min=0, max=2147483647, control_after_generate=True, tooltip="API models are not deterministic: the seed only makes the node run again."),
                *[io.Image.Input(f"image_{i}", optional=True, raw_link=True, tooltip="A reference picture (identity, place). Beyond what the model takes they are left out; LTX starts from the first.") for i in range(1, N_IMAGES + 1)],
                io.Image.Input("reference_frames", optional=True, raw_link=True, tooltip="The frames of a reference video (they are made a video again for the models that take one)."),
                io.Float.Input("reference_fps", default=24.0, min=1.0, max=120.0, step=0.001, optional=True, tooltip="The fps of reference_frames."),
                io.Audio.Input("reference_audio", optional=True, raw_link=True, tooltip="The music slice or the voice of the shot, for the models that take an audio reference."),
                io.Boolean.Input("use_image_6", default=True, optional=True, tooltip="Wire it to the switch that decides whether image_6 exists (the empty plate of the place): a lazy switch with nothing to give hands the API node an empty picture, which it refuses."),
            ],
            outputs=[
                io.Image.Output(display_name="images"),
                io.Audio.Output(display_name="audio"),
                io.Float.Output(display_name="fps"),
            ],
            enable_expand=True,
            hidden=[io.Hidden.dynprompt],
        )

    @classmethod
    def execute(cls, generator, prompt, seconds, aspect_ratio, resolution, generate_audio, seed, reference_fps=24.0, use_image_6=True, **media) -> io.NodeOutput:
        if generator not in API:
            raise MajoorError(f"Generate Shot (API) needs an API model, got '{generator}'. Available: {API}")
        graph = GraphBuilder()
        images = [media.get(f"image_{i}") for i in range(1, N_IMAGES + 1)]
        if not use_image_6:
            images[5] = None
        frames, audio = media.get("reference_frames"), media.get("reference_audio")
        videos = []
        if is_link(frames):
            videos.append(graph.node("CreateVideo", images=frames, fps=reference_fps).out(0))
        request = build_request(
            generator, prompt=prompt, seconds=seconds, aspect=aspect_ratio, resolution=resolution, audio=generate_audio, seed=seed,
            images=[h for h in images if is_link(h)], videos=videos, audios=[audio] if is_link(audio) else [],
        )
        seconds_asked = float(request.inputs["model.duration"])
        price = evaluate(badge_of(request.class_type), request.inputs, request.media)  # the badge of the node that is about to be called, on the settings of this take
        budget_seconds, budget_usd = api_budget(cls.hidden.dynprompt)
        try:  # the budget of the run: this take is counted before the model is called
            spent_seconds, spent_usd = LEDGER.charge(str(getattr(PromptServer.instance, "last_prompt_id", "") or "run"), seconds_asked, budget_seconds, price.high if price else 0.0, budget_usd)
        except ValueError as e:
            raise MajoorError(str(e)) from e
        print(f"[Majoor] Generate Shot: {generator} {seconds_asked:g} s" + (f", about {price.text}" if price else "") + f" (this run: {spent_seconds:g} s" + (f", about ${spent_usd:.2f}" if price else "") + ")")
        for note in request.notes:
            print(f"[Majoor] Generate Shot: {note}")
        api = graph.node(request.class_type, **request.inputs)
        parts = graph.node("GetVideoComponents", video=api.out(0))
        return io.NodeOutput(parts.out(0), parts.out(1), parts.out(2), expand=graph.finalize())
