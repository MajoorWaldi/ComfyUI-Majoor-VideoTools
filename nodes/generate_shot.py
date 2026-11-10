import uuid
from pathlib import Path

from comfy_api.latest import io
from comfy_execution.graph_utils import GraphBuilder

from server import PromptServer

from ..core.api_request import ASPECTS, RESOLUTIONS, build_request
from ..core.cost_guard import DEFAULT_BUDGET_SECONDS, Ledger
from ..core.pricing import badge_of, evaluate
from ..core.errors import MajoorError
from ..core.generators import list_generators, load_generator

API = [g for g in list_generators("video") if load_generator(g).source == "api"]
N_IMAGES = 9


def _ledger_path() -> Path | None:
    try:
        import folder_paths
        return Path(folder_paths.get_user_directory()) / "majoor_videotools" / "api_ledger.json"
    except Exception:  # outside ComfyUI: the count stays in memory
        return None


LEDGER = Ledger(_ledger_path())
# The references of the takes being made, handed to the API node of the expanded graph (a node can only be wired to a node): one entry per prompt,
# each token is taken out when its Held node reads it, and what a prompt left behind (a take that stopped) is dropped when the next prompt holds.
HELD: dict[str, dict[str, object]] = {}


def _prompt_id() -> str:
    return str(getattr(PromptServer.instance, "last_prompt_id", "") or "run")


def hold(value, run: str | None = None) -> str:
    run = run or _prompt_id()
    for old in [r for r in HELD if r != run]:
        del HELD[old]
    token = uuid.uuid4().hex
    HELD.setdefault(run, {})[token] = value
    return token


def take_held(token: str, what: str):
    for held in HELD.values():
        if token in held:
            return held.pop(token)
    raise MajoorError(f"The {what} held for this take is gone (the graph was run again): run the shot again.")


def api_budget(dynprompt) -> tuple[int, float, str]:
    """MAX API SECONDS, MAX API USD and the budget key of the Generator Select of the graph being run (the defaults when the graph has none or they are wired)."""
    for node_id in dynprompt.all_node_ids():
        node = dynprompt.get_node(node_id)
        if node.get("class_type") == "MajoorGeneratorSelect":
            inputs = node.get("inputs", {})
            seconds, usd, key = inputs.get("max_api_seconds", DEFAULT_BUDGET_SECONDS), inputs.get("max_api_usd", 0.0), inputs.get("budget_key", "")
            return ((DEFAULT_BUDGET_SECONDS if isinstance(seconds, list) else int(seconds)), (0.0 if isinstance(usd, list) else float(usd)),
                    ("" if not isinstance(key, str) else key.strip()))
    return DEFAULT_BUDGET_SECONDS, 0.0, ""


def budget_run(key: str) -> str:
    """The run the takes are counted in: the budget key of Generator Select, or the prompt being run."""
    return f"key:{key}" if key else _prompt_id()


class MajoorHeldImage(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(node_id="MajoorHeldImage", display_name="Held Image (internal)", category="Majoor/VideoTools/internal", is_dev_only=True,
                         description="Gives the picture that Generate Shot (API) holds for its API node. Created by Generate Shot, never wired by hand.",
                         inputs=[io.String.Input("token")], outputs=[io.Image.Output()])

    @classmethod
    def execute(cls, token) -> io.NodeOutput:
        return io.NodeOutput(take_held(token, "picture"))


class MajoorHeldAudio(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(node_id="MajoorHeldAudio", display_name="Held Audio (internal)", category="Majoor/VideoTools/internal", is_dev_only=True,
                         description="Gives the audio that Generate Shot (API) holds for its API node. Created by Generate Shot, never wired by hand.",
                         inputs=[io.String.Input("token")], outputs=[io.Audio.Output()])

    @classmethod
    def execute(cls, token) -> io.NodeOutput:
        return io.NodeOutput(take_held(token, "audio"))


class MajoorHeldVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(node_id="MajoorHeldVideo", display_name="Held Video (internal)", category="Majoor/VideoTools/internal", is_dev_only=True,
                         description="Gives the video that Generate Shot (API) holds for its API node. Created by Generate Shot, never wired by hand.",
                         inputs=[io.String.Input("token")], outputs=[io.Video.Output()])

    @classmethod
    def execute(cls, token) -> io.NodeOutput:
        return io.NodeOutput(take_held(token, "video"))


class MajoorGenerateShot(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorGenerateShot",
            display_name="Generate Shot (API)",
            category="Majoor/VideoTools",
            description="Makes the take of a shot with an API video model (Seedance, Wan, LTX...) chosen by the generator of Generator Select, from the same settings whatever the model: "
                        "the node it needs is created when the graph runs, so only the chosen model is called and paid for. "
                        "A reference that is not there (a switch with nothing to give) is left out; pictures a model does not take are left out too; "
                        "a model that needs a picture or video of the shot and gets none stops with a clear message.",
            inputs=[
                io.String.Input("generator", force_input=True, tooltip="The generator of Generator Select (an API model; the local H3 has its own branch)."),
                io.String.Input("prompt", force_input=True, tooltip="The prompt of the shot."),
                io.Float.Input("seconds", default=5.0, min=1.0, max=60.0, step=0.01, force_input=True, tooltip="generation_seconds of Select Shot or Generator Limits: the model is asked for these whole seconds."),
                io.Combo.Input("aspect_ratio", options=list(ASPECTS), default="16:9", tooltip="LTX makes 16:9 and 9:16 only."),
                io.Combo.Input("resolution", options=list(RESOLUTIONS), default="720p", tooltip="Higher costs more. LTX makes 720p and 1080p only."),
                io.Boolean.Input("generate_audio", default=True, tooltip="The model makes its own sound for the take."),
                io.Int.Input("seed", default=0, min=0, max=2147483647, control_after_generate=True, tooltip="API models are not deterministic: the seed only makes the node run again."),
                *[io.Image.Input(f"image_{i}", optional=True, tooltip="A reference picture (identity, place). A batch gives its first picture; beyond what the model takes they are left out; LTX starts from the first.") for i in range(1, N_IMAGES + 1)],
                io.Image.Input("reference_frames", optional=True, tooltip="The frames of a reference video (they are made a video again for the models that take one)."),
                io.Float.Input("reference_fps", default=24.0, min=1.0, max=120.0, step=0.001, optional=True, tooltip="The fps of reference_frames."),
                io.Audio.Input("reference_audio", optional=True, tooltip="The music slice or the voice of the shot, for the models that take an audio reference."),
                io.Combo.Input("task", options=["reference", "edit"], default="reference", optional=True, tooltip="reference: a new video made from the references. edit (Remix): the model changes source_video, the pictures say who replaces whom; it keeps the length and the format of the source."),
                io.Video.Input("source_video", optional=True, tooltip="The video of the shot (Select Shot). With task=edit it is the video that is changed."),
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
    def execute(cls, generator, prompt, seconds, aspect_ratio, resolution, generate_audio, seed, reference_fps=24.0, task="reference", **media) -> io.NodeOutput:
        if generator not in API:
            raise MajoorError(f"Generate Shot (API) needs an API model, got '{generator}'. Available: {API}")
        graph = GraphBuilder()

        def held(kind: str, value):
            return graph.node(kind, token=hold(value)).out(0)

        images = []
        for i in range(1, N_IMAGES + 1):
            picture = media.get(f"image_{i}")
            if picture is not None:  # an input that was wired to a switch with nothing to give arrives empty: it is left out
                images.append(held("MajoorHeldImage", picture[:1]))
        frames, audio, source = media.get("reference_frames"), media.get("reference_audio"), media.get("source_video")
        videos = []
        if task == "edit":
            if source is not None:
                videos.append(held("MajoorHeldVideo", source))
        elif frames is not None:
            videos.append(graph.node("CreateVideo", images=held("MajoorHeldImage", frames), fps=reference_fps).out(0))
        request = build_request(
            generator, prompt=prompt, seconds=seconds, aspect=aspect_ratio, resolution=resolution, audio=generate_audio, seed=seed,
            images=images, videos=videos, audios=[held("MajoorHeldAudio", audio)] if audio is not None else [], task=task,
        )
        seconds_asked = float(request.inputs["model.duration"])
        price = evaluate(badge_of(request.class_type), request.inputs, request.media)  # the badge of the node that is about to be called, on the settings of this take
        budget_seconds, budget_usd, key = api_budget(cls.hidden.dynprompt)
        try:  # the budget of the run: this take is counted before the model is called; an unknown price with a budget in dollars is refused
            spent_seconds, spent_usd = LEDGER.charge(budget_run(key), seconds_asked, budget_seconds, price.high if price else None, budget_usd)
        except ValueError as e:
            raise MajoorError(str(e)) from e
        print(f"[Majoor] Generate Shot: {generator} {seconds_asked:g} s" + (f", about {price.text}" if price else "") + f" (this run: {spent_seconds:g} s" + (f", about ${spent_usd:.2f}" if price else "") + ")")
        for note in request.notes:
            print(f"[Majoor] Generate Shot: {note}")
        api = graph.node(request.class_type, **request.inputs)
        parts = graph.node("GetVideoComponents", video=api.out(0))
        return io.NodeOutput(parts.out(0), parts.out(1), parts.out(2), expand=graph.finalize())
