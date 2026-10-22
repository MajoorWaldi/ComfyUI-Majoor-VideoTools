"""The five ways to start an edit. The nodes of a graph carry `properties.majoor_mode` ({"modes": [...], "toggle": "reference_2", "values": {...}, "planner": true}),
read by web/majoor_mode.js. What each mode asks of the planner is a skill file of kind `mode` (`mode_<name>.md`): its header gives the profile, the genre and
reference_mode of the planner (the remix: the pose strength), and whether the reference video of H3 is used (reference_video), its text the instructions added to the planner (the remix: the replacement instruction)."""
from .errors import MajoorError
from .skills import load_skill

MODES = {
    "image_to_edit": "a character or a product picture and a brief: the system plans the shots and generates them",
    "reference_to_edit": "a video gives the rhythm, the transitions and the energy; the sequence is recreated with new content",
    "music_to_edit": "the music sets the timing, the accelerations, the breaths and the accents",
    "text_to_edit": "a script or a brief, no picture: the system plans a storyboard, then the edit",
    "remix_replace": "an existing edit is cut into shots and some are replaced, the others are kept",
}
# the three modes the Edit Mode node offers by name; the other two stay under "Advanced", where the mode is chosen by hand
PRESETS = {"Image to Reel": "image_to_edit", "Remix": "remix_replace", "Music Edit": "music_to_edit"}
ADVANCED = "Advanced"
STYLE_DEFAULT = "Mode default"
MAX_REFERENCES = 5
PREFIX = "mode_"


def mode_settings(mode: str) -> dict:
    """What the mode skill says: profile, genre, reference_mode and extra_instructions for the planner; pose_strength and remix_instruction for the remix; whether the reference video of H3 is used (reference_video); what the mode asks of the prompt enhancer (enhancer)."""
    if mode not in MODES:
        raise MajoorError(f"Unknown mode '{mode}'. Available: {list(MODES)}")
    skill = load_skill(PREFIX + mode)
    meta, text = skill.meta, skill.body.strip()
    video, enhancer = meta.get("reference_video", "false") == "true", meta.get("enhancer", "")
    if mode == "remix_replace":
        return {"pose_strength": float(meta.get("pose_strength", 0.72)), "remix_instruction": text, "reference_video": video, "enhancer": enhancer}
    return {"reference_video": video, "enhancer": enhancer, "profile": meta.get("profile", "none"), "genre": meta.get("genre", "all"), "reference_mode": meta.get("reference_mode", "false") == "true", "extra_instructions": text}


def all_settings() -> dict[str, dict]:
    return {mode: mode_settings(mode) for mode in MODES}
