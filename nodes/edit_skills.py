import torch
import torch.nn.functional as F
from aiohttp import web
from comfy_api.latest import io

from ..core.errors import MajoorError
from ..core.profiles import DIALS, list_profiles, music_text, profile_text
from ..core.skills import DEFAULTS, GENRES, compose, load_skill, module_states, prompt_skills, user_message


def _build(skill_id, overlays_splits, text_overlays, reference_mode, genre, duration, fps, aspect_ratio, n_pictures, text_allowed, extra, profile="none", dials=None):
    skill = load_skill(skill_id)
    states = module_states(skill, overlays_splits=overlays_splits, text_overlays=text_overlays, reference_mode=reference_mode, genre=genre)
    variables = {"DURATION": f"{duration:g}" if duration > 0 else "", "FPS": f"{fps:g}" if fps > 0 else "", "ASPECT": "" if aspect_ratio == "auto" else aspect_ratio,
                 "N_PICTURES": str(n_pictures), "TEXT_ALLOWED": text_allowed}
    block = (music_text if skill.kind == "music_writer" else profile_text)(profile, **(dials or {}))  # a music gets the direction of the profile, not its camera and art direction
    text, on = compose(skill, states, variables, extra, block)
    return skill, text, on


def _stack(groups: list[torch.Tensor]) -> torch.Tensor:
    """The frames of every group in one batch on a common canvas: each group is scaled to fit it, keeping its aspect, and centered on black."""
    height, width = max(g.shape[1] for g in groups), max(g.shape[2] for g in groups)
    out = []
    for g in groups:
        if g.shape[1:3] != (height, width):
            scale = min(height / g.shape[1], width / g.shape[2])
            h, w = max(round(g.shape[1] * scale), 1), max(round(g.shape[2] * scale), 1)
            g = F.interpolate(g.movedim(-1, 1), size=(h, w), mode="bilinear", antialias=True).movedim(1, -1)
            g = F.pad(g, (0, 0, (width - w) // 2, width - w - (width - w) // 2, (height - h) // 2, height - h - (height - h) // 2))
        out.append(g)
    return torch.cat(out)


class MajoorEditSkills(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        skills = prompt_skills() or ["(no skill in the skills folder)"]
        return io.Schema(
            node_id="MajoorEditSkills",
            display_name="Edit Skills",
            category="Majoor/VideoTools",
            description="Loads a skill (a system prompt kept in the skills folder of the pack), switches its parts on or off, fills in the length, fps and aspect ratio, "
                        "and outputs the system prompt and the user message for an LLM node (Qwen VL, Ollama...). Add your own .md files to the skills folder.",
            inputs=[
                io.Combo.Input("skill", options=skills, default=skills[0], tooltip="A file of the skills folder. Its header says what it is for (planner: writes the plan of an edit; h3_writer: writes the prompt of a shot)."),
                io.Boolean.Input("overlays_splits", default=True, tooltip="The skill teaches overlays (double exposure, small windows) and split screens."),
                io.Boolean.Input("text_overlays", default=True, tooltip="The skill teaches text on the shots."),
                io.Boolean.Input("reference_mode", default=True, tooltip="The skill tells how to work on the frames of a reference video (copy its rhythm and its effects)."),
                io.Combo.Input("genre", options=["all", "none", *GENRES], default="all", tooltip="The kind of edit the skill gives advice for. all: every kind; none: no advice by kind."),
                io.Float.Input("duration", default=0.0, min=0.0, max=3600.0, step=0.1, tooltip="Seconds of the edit, written in the prompt. 0: the skill's default."),
                io.Float.Input("fps", default=0.0, min=0.0, max=240.0, step=0.001, tooltip="0: the skill's default (24)."),
                io.Combo.Input("aspect_ratio", options=["auto", "9:16", "16:9", "1:1", "4:5", "21:9"], default="auto", tooltip="auto: the skill's default (9:16)."),
                io.Int.Input("n_pictures", default=1, min=0, max=16, tooltip="How many pictures go with the message to the LLM (<Picture 1>...)."),
                io.String.Input("text_allowed", default="", tooltip="What text may be written on the shots (a brand name, a slogan...). Empty: none."),
                io.String.Input("brief", multiline=True, default="", tooltip="What the edit is about: goes into the user message."),
                io.String.Input("rhythm_text", multiline=True, default="", force_input=True, optional=True, tooltip="The EDIT RHYTHM of Create Timeline or Cut Markers: goes into the user message."),
                io.Image.Input("images", optional=True, tooltip="The reference pictures sent to the LLM, one per image of the batch. When connected, n_pictures is the size of the batch."),
                io.Image.Input("video_1", optional=True, tooltip="Frames of <Video 1> (ref_video_0 of H3), sampled from the first to the last frame. The user message tells the LLM which images of the chat they are, and the images output carries them."),
                io.Image.Input("video_2", optional=True, tooltip="Frames of <Video 2> (ref_video_1 of H3), as video_1."),
                io.String.Input("extra_instructions", multiline=True, default="", tooltip="Added at the end of the system prompt."),
                io.Combo.Input("profile", options=["none", *list_profiles()], default="none", tooltip="A starting strategy for the edit (rhythm, camera, art direction), added to the system prompt. Never a restriction: the brief wins. Not used by music skills."),
                *[io.Combo.Input(name, options=["auto", *levels], default="auto", tooltip="auto: the value of the profile. Otherwise it replaces it.") for name, levels in DIALS.items()],
            ],
            outputs=[io.String.Output(display_name="system_prompt"), io.String.Output(display_name="user_message"), io.String.Output(display_name="info"),
                     io.Image.Output(display_name="images", tooltip="The pictures, then the frames of <Video 1> and <Video 2>, in the order the user message announces: connect it to the LLM instead of the pictures alone. Empty when no image is connected.")],
        )

    @classmethod
    def execute(cls, skill, overlays_splits, text_overlays, reference_mode, genre, duration, fps, aspect_ratio, n_pictures, text_allowed, brief, extra_instructions, profile, cut_density, transition_intensity, creative_freedom, reference_fidelity, narrative_coherence, rhythm_text="", images=None, video_1=None, video_2=None) -> io.NodeOutput:
        n_pictures = images.shape[0] if images is not None else n_pictures
        groups, videos, count = ([images] if images is not None else []), [], (images.shape[0] if images is not None else 0)
        for k, frames in ((1, video_1), (2, video_2)):
            if frames is not None:
                videos.append((k, count + 1, count + frames.shape[0]))
                groups.append(frames)
                count += frames.shape[0]
        loaded, text, on = _build(skill, overlays_splits, text_overlays, reference_mode, genre, duration, fps, aspect_ratio, n_pictures, text_allowed, extra_instructions, profile,
                                   dict(cut_density=cut_density, transition_intensity=transition_intensity, creative_freedom=creative_freedom, reference_fidelity=reference_fidelity, narrative_coherence=narrative_coherence))
        info = f"{loaded.name} ({loaded.kind}): {len(text.split())} words; parts on: {', '.join(on) or 'none'}"
        return io.NodeOutput(text, user_message(brief, rhythm_text, n_pictures, tuple(videos)), info, _stack(groups) if groups else None)


def register_routes() -> None:
    from server import PromptServer

    routes = PromptServer.instance.routes

    @routes.get("/majoor/skills")
    async def skills(request):
        try:
            return web.json_response({"skills": prompt_skills(), "profiles": ["none", *list_profiles()], "defaults": DEFAULTS})
        except MajoorError as e:
            return web.json_response({"error": str(e)}, status=400)

    @routes.post("/majoor/skills/compose")
    async def skills_compose(request):
        try:
            body = await request.json()
            skill, text, on = _build(str(body["skill"]), bool(body.get("overlays_splits", True)), bool(body.get("text_overlays", True)), bool(body.get("reference_mode", True)),
                                     str(body.get("genre", "all")), float(body.get("duration", 0)), float(body.get("fps", 0)), str(body.get("aspect_ratio", "auto")),
                                     int(body.get("n_pictures", 1)), str(body.get("text_allowed", "")), str(body.get("extra_instructions", "")),
                                     str(body.get("profile", "none")), {name: str(body.get(name, "auto")) for name in DIALS})
        except MajoorError as e:
            return web.json_response({"error": str(e)}, status=400)
        except (KeyError, TypeError, ValueError) as e:
            return web.json_response({"error": f"Invalid request: {e!r}"}, status=400)
        return web.json_response({"name": skill.name, "kind": skill.kind, "text": text, "words": len(text.split()), "modules": on})
