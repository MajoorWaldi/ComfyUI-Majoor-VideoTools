import math

import torch
import torch.nn.functional as F
from aiohttp import web
from comfy_api.latest import io

from ..core.errors import MajoorError
from ..core.dialogue import lines_of_shot
from ..core.profiles import DIALS, list_profiles, music_text, profile_text
from ..core.skills import DEFAULTS, GENRES, compose, load_skill, module_states, prompt_skills, user_message


RATIOS = ("9:16", "16:9", "1:1", "4:5", "21:9", "2:3", "3:2", "3:4", "4:3")


def _build(skill_id, overlays_splits, text_overlays, reference_mode, genre, duration, fps, aspect_ratio, n_pictures, text_allowed, extra, profile="none", dials=None, dialogue=False, locations=False, plate=False):
    skill = load_skill(skill_id)
    states = module_states(skill, overlays_splits=overlays_splits, text_overlays=text_overlays, reference_mode=reference_mode, genre=genre, dialogue=dialogue, locations=locations, plate=plate)
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
                        "and outputs the system prompt and the user message for an LLM node (Generate Text with Qwen VL or Gemma...). Add your own .md files to the skills folder.",
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
                io.Image.Input("plate", optional=True, tooltip="The empty plate of the place of the shot (one image, the last picture: <Picture N>). The message announces it and the skill uses it for the place only; the images output carries it after the pictures."),
                io.Audio.Input("voice", optional=True, tooltip="The voice sample of <Subject 1> (ref_audio_0 of H3). Connected, the message announces <Audio 1> and the skill speaks the dialogue in it."),
                io.String.Input("extra_instructions", multiline=True, default="", tooltip="Added at the end of the system prompt."),
                io.Combo.Input("profile", options=["none", *list_profiles()], default="none", tooltip="A starting strategy for the edit (rhythm, camera, art direction), added to the system prompt. Never a restriction: the brief wins. Not used by music skills."),
                *[io.Combo.Input(name, options=["auto", *levels], default="auto", tooltip="auto: the value of the profile. Otherwise it replaces it.") for name, levels in DIALS.items()],
                io.String.Input("dialogue", multiline=True, default="", optional=True, tooltip="The lines of the edit, each with the times of the edit where it is spoken, for example: 0-3 s: \"Welcome.\" A shot gets the lines that start inside it (the times of the shot are read in its rhythm_text), with their times counted from its start. Empty: no dialogue."),
                io.Boolean.Input("locations", default=False, optional=True, tooltip="The planner skill asks for a `location` in every shot: the place, one sentence, the same word for word for the shots that happen in it (the empty plate of each place is generated once)."),
                io.Int.Input("width", default=0, min=0, max=4096, optional=True, tooltip="With height: the size of the video in pixels. The prompt then names the closest ratio, instead of aspect_ratio. Connect Resolution Selector."),
                io.Int.Input("height", default=0, min=0, max=4096, optional=True, tooltip="See width."),
                io.Float.Input('shot_start',default=-1.0,min=-1.0,max=3600.0,optional=True,tooltip='Numeric start of this shot for dialogue; -1 reads the rhythm text.'),
                io.Float.Input('shot_duration',default=0.0,min=0.0,max=3600.0,optional=True,tooltip='Numeric target duration of this shot for dialogue.'),
            ],
            outputs=[io.String.Output(display_name="system_prompt"), io.String.Output(display_name="user_message"), io.String.Output(display_name="info"),
                     io.Image.Output(display_name="images", tooltip="The pictures, then the frames of <Video 1> and <Video 2>, in the order the user message announces: connect it to the LLM instead of the pictures alone. Empty when no image is connected.")],
        )

    @classmethod
    def execute(cls, skill, overlays_splits, text_overlays, reference_mode, genre, duration, fps, aspect_ratio, n_pictures, text_allowed, brief, extra_instructions, profile, cut_density, transition_intensity, creative_freedom, reference_fidelity, narrative_coherence, rhythm_text="", images=None, video_1=None, video_2=None, voice=None, dialogue="", plate=None, locations=False, width=0, height=0, shot_start=-1.0, shot_duration=0.0) -> io.NodeOutput:
        n_pictures = (images.shape[0] if images is not None else n_pictures) + (plate is not None)
        groups, videos, count = ([images] if images is not None else []), [], (images.shape[0] if images is not None else 0)
        if plate is not None:  # the empty plate of the place: the last picture
            groups.append(plate[:1])
            count += 1
        for frames in (video_1, video_2):  # numbered in the order they are present, as H3 numbers its reference videos
            if frames is not None:
                videos.append((len(videos) + 1, count + 1, count + frames.shape[0]))
                groups.append(frames)
                count += frames.shape[0]
        if width and height:
            aspect_ratio = min(RATIOS, key=lambda r: abs(math.log(width / height / (int(r.split(':')[0]) / int(r.split(':')[1])))))
        spoken = lines_of_shot(rhythm_text,dialogue,shot_start if shot_start>=0 and shot_duration>0 else None,shot_start+shot_duration if shot_start>=0 and shot_duration>0 else None)
        loaded, text, on = _build(skill, overlays_splits, text_overlays, reference_mode, genre, duration, fps, aspect_ratio, n_pictures, text_allowed, extra_instructions, profile,
                                   dict(cut_density=cut_density, transition_intensity=transition_intensity, creative_freedom=creative_freedom, reference_fidelity=reference_fidelity, narrative_coherence=narrative_coherence),
                                   dialogue=voice is not None or bool(spoken), locations=locations, plate=plate is not None)
        info = f"{loaded.name} ({loaded.kind}): {len(text.split())} words; parts on: {', '.join(on) or 'none'}"
        return io.NodeOutput(text, user_message(brief, rhythm_text, n_pictures, tuple(videos), voice is not None, spoken, plate is not None, shot_only=skill == 'h3_shot_prompt_from_plan'), info, _stack(groups) if groups else None)


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
                                     str(body.get("profile", "none")), {name: str(body.get(name, "auto")) for name in DIALS}, bool(body.get("dialogue", False)), bool(body.get("locations", False)), bool(body.get("plate", False)))
        except MajoorError as e:
            return web.json_response({"error": str(e)}, status=400)
        except (KeyError, TypeError, ValueError) as e:
            return web.json_response({"error": f"Invalid request: {e!r}"}, status=400)
        return web.json_response({"name": skill.name, "kind": skill.kind, "text": text, "words": len(text.split()), "modules": on})
