import asyncio
import json
from urllib.parse import urlparse
from urllib.request import urlopen

from aiohttp import web
from comfy_api.latest import io

from ..core.errors import MajoorError
from ..core.modes import ADVANCED, MAX_REFERENCES, MODES, PRESETS, STYLE_DEFAULT, all_settings, mode_settings
from ..core.preflight import LOOPBACK, ollama_problems
from ..core.profiles import list_profiles


class MajoorEditMode(io.ComfyNode):
    """Never executed: it only holds the mode, and web/majoor_mode.js turns the nodes tagged for each mode on or off."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        remix = mode_settings("remix_replace")
        return io.Schema(
            node_id="MajoorEditMode",
            display_name="Edit Mode",
            category="Majoor/VideoTools",
            description="One choice for the whole graph: image, reference video, music, text or remix. The nodes tagged for a mode are enabled or bypassed, "
                        "the rhythm source and the shot list switch are set, and the planner gets the profile, genre and instructions of the mode. "
                        "In remix mode the pose strength and the replacement instruction are written into every shot block.",
            inputs=[
                io.Combo.Input("preset", options=[*PRESETS, ADVANCED], default=next(iter(PRESETS)), tooltip="The three ways to start: " + ", ".join(f"{name} ({MODES[mode]})" for name, mode in PRESETS.items()) + f". {ADVANCED}: choose any of the five modes below."),
                io.Combo.Input("style", options=[STYLE_DEFAULT, "none", *list_profiles()], default=STYLE_DEFAULT, tooltip="The editing profile of the planner and of the music (rhythm, camera, art direction). 'Mode default': the one the mode asks for."),
                io.Combo.Input("mode", options=list(MODES), default=next(iter(MODES)), tooltip="\n".join(f"{name}: {words}" for name, words in MODES.items())),
                *[io.Boolean.Input(f"reference_{k}", default=False, tooltip=f"Use reference picture {k} (a product, an outfit, a place...). Up to {MAX_REFERENCES} pictures with the main one.") for k in range(2, MAX_REFERENCES + 1)],
                io.Boolean.Input("pose_control", default=True, tooltip="Remix: use the pose ControlNet of H3. It is always off in the other modes (the shots are placeholder cards)."),
                io.Float.Input("pose_strength", default=remix["pose_strength"], min=0.0, max=1.0, step=0.01, tooltip="Remix: strength of the pose ControlNet that H3 drives from the pose of the original shot (the body positions and the motion are kept)."),
                io.String.Input("remix_instruction", multiline=True, default=remix["remix_instruction"], tooltip="Remix: what to replace, written into the edit request of every shot block. Empty: the blocks keep their own."),
                io.Boolean.Input("reference_video", default=True, tooltip="Use the reference video (<Video 1> of H3 and of the LLM): the nodes tagged for it are enabled, bypassed when it is off."),
            ],
            outputs=[],
        )

    @classmethod
    def execute(cls, **kwargs) -> io.NodeOutput:
        return io.NodeOutput()


def installed_models(url: str) -> list[str] | None:
    """The models that the Ollama at this address has, None when it does not answer. Only an Ollama on this machine is asked."""
    try:
        with urlopen(url.rstrip("/") + "/api/tags", timeout=2) as response:
            return [m["name"] for m in json.load(response)["models"]]
    except (OSError, ValueError, KeyError):
        return None


def register_routes() -> None:
    from server import PromptServer

    @PromptServer.instance.routes.get("/majoor/modes")
    async def modes(request):
        """What the mode skills say, read again at every call: a skill file edited in the folder is used at once."""
        try:
            return web.json_response({"modes": all_settings(), "presets": PRESETS})
        except MajoorError as e:
            return web.json_response({"error": str(e)}, status=400)

    @PromptServer.instance.routes.post("/majoor/preflight")
    async def preflight(request):
        """What would fail in the Ollama of the graph: {"ollama": [{"url", "model"}]} gives {"problems": [...]}. Only the Ollama of this machine is asked."""
        asked = [(str(o.get("url", "")), str(o.get("model", ""))) for o in (await request.json()).get("ollama", [])]
        local = {url for url, _ in asked if urlparse(url).hostname in LOOPBACK}
        installed = dict(zip(local, await asyncio.gather(*(asyncio.to_thread(installed_models, url) for url in local))))
        return web.json_response({"problems": ollama_problems([(u, m) for u, m in asked if u in local], installed)})
