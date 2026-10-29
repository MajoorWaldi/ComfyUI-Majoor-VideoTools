from aiohttp import web
from comfy_api.latest import io

from ..core.errors import MajoorError
from ..core.camera import CAMERAS, NONE, camera_text
from ..core.modes import MAX_REFERENCES, MODES, STYLE_DEFAULT, all_settings, mode_settings
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
            description="One choice for the whole graph: creative or remix, with a video, a reference video and a music of your own as options. The nodes tagged for a mode and its options are enabled or bypassed, "
                        "the rhythm source and the shot list switch are set, and the planner gets the profile, genre and instructions of the mode. "
                        "In remix mode the pose strength and the replacement instruction are written into every shot block.",
            inputs=[
                io.Combo.Input("style", options=[STYLE_DEFAULT, "none", *list_profiles()], default=STYLE_DEFAULT, tooltip="The editing profile of the planner and of the music (rhythm, camera, art direction). 'Mode default': the one the mode asks for."),
                io.Combo.Input("mode", options=list(MODES), default=next(iter(MODES)), tooltip="\n".join(f"{name}: {words}" for name, words in MODES.items())),
                *[io.Boolean.Input(f"reference_{k}", default=False, tooltip=f"Use reference picture {k} (a product, an outfit, a place...). Up to {MAX_REFERENCES} pictures with the main one.") for k in range(2, MAX_REFERENCES + 1)],
                io.Boolean.Input("pose_control", default=True, tooltip="Remix: use the pose ControlNet of H3. It is always off in the other modes (the shots are placeholder cards)."),
                io.Float.Input("pose_strength", default=remix["pose_strength"], min=0.0, max=1.0, step=0.01, tooltip="Remix: strength of the pose ControlNet that H3 drives from the pose of the original shot (the body positions and the motion are kept)."),
                io.String.Input("remix_instruction", multiline=True, default=remix["remix_instruction"], tooltip="Remix: what to replace, written into the edit request of every shot block. Empty: the blocks keep their own."),
                io.Boolean.Input("from_video", default=False, tooltip="Creative: the MOTION VIDEO gives the rhythm of the edit and the motion and camera of the shots (<Video 1>). Always on in the remix, where it is the video to remix."),
                io.Boolean.Input("ref_video", default=False, tooltip="Use the REF VIDEO as one more reference for the LLM and for H3 (<Video 2>)."),
                io.Boolean.Input("own_music", default=False, tooltip="Creative: use the MUSIC file and cut the edit on its beats, in place of a music generated for the edit."),
                io.Boolean.Input("voice", default=False, tooltip="Use the VOICE file as the voice of the subject: H3 speaks the DIALOGUE in it, and the shots keep their own audio (the voice) instead of the master soundtrack."),
                io.Combo.Input("camera", options=[NONE, *CAMERAS], default=NONE, tooltip="Creative: the camera, the lens and the aperture of the whole edit, written into every shot.\n" + "\n".join(f"{name}: {words}" for name, words in CAMERAS.items())),
                io.Boolean.Input("quality_check", default=False, tooltip="Remix: a judge compares every generated take with <Picture 1> and its prompt; a failed take is generated once more with the fault in the prompt (slower: one more LLM call per shot, one more H3 run for a failed one)."),
            ],
            outputs=[],
        )

    @classmethod
    def execute(cls, **kwargs) -> io.NodeOutput:
        return io.NodeOutput()


def register_routes() -> None:
    from server import PromptServer

    @PromptServer.instance.routes.get("/majoor/modes")
    async def modes(request):
        """What the mode skills say, read again at every call: a skill file edited in the folder is used at once."""
        try:
            return web.json_response({"modes": all_settings(), "cameras": {look: camera_text(look) for look in CAMERAS}})
        except MajoorError as e:
            return web.json_response({"error": str(e)}, status=400)
