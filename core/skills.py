"""Skills: system prompts kept as files in the skills/ folder of the pack, loaded by name and assembled by the Edit Skills node.

A skill file is a Markdown or text file:

    ---
    name: Dynamic Edit
    kind: planner            (planner | h3_writer | music_writer | analyzer | profile | mode | other)
    description: one line
    ---
    text that is always there, with {{VARIABLES}} such as {{DURATION}}
    <<module overlays_splits>>
    text that is only there when that module is on
    <<end>>
    <<module example>>
    {"a plan": "as JSON, cleaned of the effects that are turned off"}
    <<end>>

A module is on or off by the settings of the node; "default=off" in the marker gives the value when nothing says otherwise.
A module can sit inline inside a sentence, and inside another module (the text is there when all of them are on)."""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .errors import MajoorError

SKILLS = Path(__file__).resolve().parents[1] / "skills"
KINDS = ("planner", "h3_writer", "music_writer", "analyzer", "profile", "mode", "other")
DATA_KINDS = ("profile", "mode")  # not system prompts: an editing profile, the settings of an edit mode (see core/profiles.py and core/modes.py)
# a module alone on its lines, or inline inside a sentence
_OPEN = re.compile(r"<<module ([a-z0-9_]+)(?: default=(on|off))?>>(\n)?")
_END = "<<end>>"
VARIABLE = re.compile(r"\{\{([A-Z_]+)\}\}")
DEFAULTS = {"DURATION": "8", "FPS": "24", "ASPECT": "9:16", "N_PICTURES": "1", "TEXT_ALLOWED": "none"}
GENRES = ("character", "product_ad", "motion_graphics", "ugc", "trailer")


@dataclass
class Part:
    text: str
    modules: tuple[tuple[str, bool], ...] = ()  # the modules the text is in, outer first, with their default; all must be on


@dataclass
class Skill:
    id: str
    name: str
    kind: str
    description: str
    parts: list[Part] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)  # the other lines of the header

    @property
    def modules(self) -> list[str]:
        return list(dict.fromkeys(name for p in self.parts for name, _ in p.modules))

    @property
    def body(self) -> str:
        """Everything the skill says with every module on, markers removed."""
        return "".join(p.text for p in self.parts)


def _parts(skill_id: str, text: str) -> list[Part]:
    parts: list[Part] = []
    stack: list[tuple[str, bool]] = []
    at = 0
    pos = 0
    while True:
        opened = _OPEN.search(text, pos)
        end = text.find(_END, pos)
        if opened is None and end < 0:
            break
        if opened is not None and (end < 0 or opened.start() < end):
            if opened.start() > at:
                parts.append(Part(text[at:opened.start()], tuple(stack)))
            stack.append((opened.group(1), opened.group(2) != "off"))
            at = pos = opened.end()
            continue
        if not stack:
            raise MajoorError(f"Skill '{skill_id}': an {_END} marker has no <<module>>")
        if end > at:
            parts.append(Part(text[at:end], tuple(stack)))
        stack.pop()
        at = pos = end + len(_END)
        if text[at:at + 1] == "\n" and (end == 0 or text[end - 1] == "\n"):  # a marker alone on its line leaves no empty line
            at = pos = at + 1
    if stack:
        raise MajoorError(f"Skill '{skill_id}': module '{stack[-1][0]}' is not closed with {_END}")
    if at < len(text):
        parts.append(Part(text[at:], ()))
    return parts


def parse_skill(skill_id: str, text: str) -> Skill:
    text = text.replace("\r\n", "\n")
    meta: dict[str, str] = {}
    if text.startswith("---\n"):
        head, closed, rest = text[4:].partition("\n---\n")
        if not closed:
            raise MajoorError(f"Skill '{skill_id}': the header is not closed with a --- line")
        for line in head.splitlines():
            key, _, value = line.partition(":")
            if key.strip():
                meta[key.strip().lower()] = value.strip()
        text = rest
    kind = meta.get("kind", "other")
    if kind not in KINDS:
        raise MajoorError(f"Skill '{skill_id}': unknown kind '{kind}'. Available: {list(KINDS)}")
    return Skill(skill_id, meta.get("name", skill_id), kind, meta.get("description", ""), _parts(skill_id, text), meta)


def list_skills(kind: str | None = None) -> list[str]:
    ids = sorted(p.stem for p in SKILLS.glob("*.md")) if SKILLS.is_dir() else []
    return [i for i in ids if kind is None or load_skill(i).kind == kind]


def prompt_skills() -> list[str]:
    """The skills that are system prompts (what the skill widget of Edit Skills offers)."""
    return [i for i in list_skills() if load_skill(i).kind not in DATA_KINDS]


def load_skill(skill_id: str) -> Skill:
    if not re.fullmatch(r"[\w .()-]+", skill_id or ""):
        raise MajoorError(f"Invalid skill name {skill_id!r}")
    path = SKILLS / f"{skill_id}.md"
    if not path.is_file():
        raise MajoorError(f"Unknown skill '{skill_id}'. Available: {list_skills()}")
    return parse_skill(skill_id, path.read_text(encoding="utf-8"))


def _strip_effects(plan_text: str, *, overlays_splits: bool, text_overlays: bool) -> str:
    """The example plan of a skill without the effects that are turned off."""
    try:
        data = json.loads(plan_text)
    except json.JSONDecodeError:
        return plan_text
    drop = [k for k, keep in (("overlay", overlays_splits), ("split", overlays_splits), ("text", text_overlays)) if not keep]

    def clean(item):
        for key in drop:
            item.pop(key, None)
        for cut in item.get("sub_cuts") or []:
            clean(cut)

    for shot in data.get("shots", []) if isinstance(data, dict) else []:
        clean(shot)
    return json.dumps(data, indent=2, ensure_ascii=False)


def module_states(skill: Skill, *, overlays_splits: bool = True, text_overlays: bool = True, reference_mode: bool = True, genre: str = "all", dialogue: bool = False, locations: bool = False, plate: bool = False) -> dict[str, bool]:
    """Which modules of a skill are on, from the settings of the node. Modules the settings do not know keep their default."""
    if genre not in ("all", "none", *GENRES):
        raise MajoorError(f"Unknown genre '{genre}'. Available: {['all', 'none', *GENRES]}")
    states = {"overlays_splits": overlays_splits, "text_overlays": text_overlays, "reference_mode": reference_mode, "genre_header": genre != "none", "dialogue": dialogue, "locations": locations, "plate": plate}
    for g in GENRES:
        states[f"genre_{g}"] = genre == "all" or genre == g
    states.update({f"not_{name}": not on for name, on in list(states.items())})  # not_X is on when X is off
    return {m: states[m] for m in skill.modules if m in states}


def compose(skill: Skill, states: dict[str, bool] | None = None, variables: dict[str, str] | None = None, extra: str = "", profile: str = "") -> tuple[str, list[str]]:
    """The system prompt: the always-there text, the modules that are on, the variables filled in, the editing profile, the extra instructions of the user at the end.
    Returns (text, names of the modules that are on)."""
    states = states or {}
    values = {**DEFAULTS, **{k.upper(): str(v) for k, v in (variables or {}).items() if str(v).strip()}}
    flags = {"overlays_splits": states.get("overlays_splits", True), "text_overlays": states.get("text_overlays", True)}
    out, on = [], []
    for part in skill.parts:
        if not all(states.get(name, default) for name, default in part.modules):
            continue
        text = part.text
        if any(name == "example" for name, _ in part.modules):
            text = _strip_effects(text.strip(), **flags) + "\n"
        on += [name for name, _ in part.modules]
        out.append(text)
    text = VARIABLE.sub(lambda m: values.get(m.group(1), ""), "".join(out))
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    if profile.strip():
        text += "\n" + profile.strip() + "\n"
    if extra.strip():
        text += f"\nEXTRA INSTRUCTIONS FROM THE USER (they come first when they contradict the rules above about style, subject or length)\n{extra.strip()}\n"
    return text, list(dict.fromkeys(on))


def user_message(brief: str = "", rhythm_text: str = "", n_pictures: int = 1, videos: tuple[tuple[int, int, int], ...] = (), voice: bool = False, dialogue: str = "", plate: bool = False, shot_only: bool = False) -> str:
    """The message that goes with the skill: the brief, the pictures, the videos, the voice, the dialogue, the rhythm. videos: (number, first image, last image) of the frames of each <Video k> among the images of the chat."""
    blocks = []
    if shot_only:
        blocks.append('H3 INPUT MODE: ' + ('Ref2VA' if n_pictures > 0 or videos or voice else 'T2VA'))
    scoped = shot_only and bool(rhythm_text.strip())
    if scoped:
        blocks.append("CURRENT SHOT ONLY\nThe selected shot below is the complete local generation brief. Perform only its visible event, starting state and ending state. Do not reconstruct the whole film. References define identity, not a repeated action or setting. After this event, hold its resulting state for any unused take duration; do not start the next event or replay the action.")
    if shot_only:
        local = rhythm_text if scoped else brief
        if re.search(r'\b(hesitat\w*|listen\w*|reassur\w*|emotion\w*|sad|grief|reaction|triste|hésit\w*|écout\w*)\b',local,re.I):
            blocks.append('LOCAL PERFORMANCE\nExpress the stated intention through one observable response to the existing scene. Give the gaze a relevant target; let the reaction change the inherited state. Keep it restrained. Add no dialogue, obstacle or additional action that the local brief does not support.')
        if re.search(r'\b(anamorphic|anamorphique|bokeh|flare|rack focus|profondeur de champ)\b',local,re.I):
            blocks.append('LOCAL OPTICS\nMake the requested optical character visible through the existing focus subject, depth layers and light sources. Describe camera movement as type, range and pace only where useful. Preserve the requested format and visual style; do not add a lens flare without a supported light source.')
    if brief.strip() and not scoped:
        blocks.append("BRIEF\n" + brief.strip())
    if n_pictures > 0:
        blocks.append("PICTURES\n" + " ".join(f"<Picture {i}>" for i in range(1, n_pictures + 1)) + " are the images of this chat, in order.")
    if plate:
        blocks.append(f"PLACE\n<Picture {n_pictures}> is the empty plate of the place of this shot: unoccupied but set-dressed, with its relevant furniture, mounted artwork, practical lights and fixed objects. Preserve their appearance and placement and name the elements useful to this shot in the prompt. It is an environment reference, never the actor identity. Static printed figures remain part of the artwork unless this shot explicitly animates them; movable/action props follow the current shot state.")
    if videos:
        blocks.append("VIDEOS\n" + "\n".join(f"<Video {k}> = images {a} to {b} of this chat ({b - a + 1} frames in time order, from the first to the last frame of the clip)." for k, a, b in videos))
    if voice:
        blocks.append("AUDIO\n<Audio 1> = the voice sample of <Subject 1>: H3 receives it and speaks the lines of the DIALOGUE in this voice.")
    if dialogue.strip():
        blocks.append("DIALOGUE (the lines spoken in this shot, with their times counted from the start of the shot)\n" + dialogue.strip())
    if rhythm_text.strip():
        blocks.append(rhythm_text.strip())
    return "\n\n".join(blocks)
