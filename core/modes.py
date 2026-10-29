"""The two ways to start an edit: creative and remix. The nodes of a graph carry `properties.majoor_mode` ({"modes": [...], "toggle": "from_video", "any": [...], "values": {...}, "planner": true}),
read by web/majoor_mode.js. What each mode asks of the planner is a skill file of kind `mode` (`mode_<name>.md`): its header gives the profile, the genre and reference_mode of the planner
(the remix: the pose strength), whether the video is used by default (from_video), what the prompt enhancer is asked, and what is added when the video is used; its text the instructions
added to the planner (the remix: the replacement instruction)."""
from .errors import MajoorError
from .skills import load_skill

MODES = {
    "creative": "a brief and pictures, with a video (its rhythm and motion) or a music of your own if you want: the system plans the shots and generates them",
    "remix_replace": "an existing edit is cut into shots and some are replaced, the others are kept",
}
STYLE_DEFAULT = "Mode default"
MAX_REFERENCES = 5
PREFIX = "mode_"


def mode_settings(mode: str) -> dict:
    """What the mode skill says. Both modes: from_video (the video is used by default) and enhancer (what the prompt enhancer is asked). Remix: pose_strength and remix_instruction.
    Creative: profile, profile_from_video, genre, reference_mode, extra_instructions and from_video_instructions (added when a video gives the rhythm) for the planner, enhancer_from_video."""
    if mode not in MODES:
        raise MajoorError(f"Unknown mode '{mode}'. Available: {list(MODES)}")
    skill = load_skill(PREFIX + mode)
    meta, text = skill.meta, skill.body.strip()
    common = {"from_video": meta.get("from_video", "false") == "true", "enhancer": meta.get("enhancer", "")}
    if mode == "remix_replace":
        return {**common, "pose_strength": float(meta.get("pose_strength", 0.72)), "remix_instruction": text}
    return {**common, "enhancer_from_video": meta.get("enhancer_from_video", ""), "profile": meta.get("profile", "none"), "profile_from_video": meta.get("profile_from_video", "none"), "genre": meta.get("genre", "all"),
            "reference_mode": meta.get("reference_mode", "false") == "true", "extra_instructions": text, "from_video_instructions": meta.get("from_video_instructions", "")}


def all_settings() -> dict[str, dict]:
    return {mode: mode_settings(mode) for mode in MODES}
