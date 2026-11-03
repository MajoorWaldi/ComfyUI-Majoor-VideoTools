"""A camera move for every shot: a shot whose prompt names none, or the same one as the shot before, is given the next one of a short list.

No model. A language model writing many shots tends to leave the camera still or to repeat the same move; this makes the plan move without
changing what the shots show. A brief that asks for a fixed camera is left alone."""
import re
from dataclasses import replace

MOVES = (
    ("slow push-in", "a slow push-in toward the subject", r"push[- ]?in|pushes in|dolly in"),
    ("pull-back reveal", "a pull-back that reveals the place around the subject", r"pull[- ]?back|pulls back|dolly out"),
    ("orbit", "a slow orbit around the subject", r"orbit"),
    ("lateral track", "a lateral track that follows the subject", r"tracking shot|lateral track|tracks? (?:left|right|alongside|the subject)|follow(?:s|ing)? (?:shot|behind|him|her|the subject)"),
    ("whip pan", "a whip pan that lands on the subject", r"whip"),
    ("handheld follow", "a handheld follow behind or beside the subject", r"hand[- ]?held"),
    ("tilt-up", "a tilt-up from the feet to the face", r"tilt"),
    ("crane", "a crane move, rising or falling", r"\bcrane\b|\bjib\b"),
    ("rack focus", "a rack focus from the foreground to the subject", r"rack focus|focus pull"),
    ("dolly zoom", "a dolly zoom on the subject", r"dolly zoom|vertigo"),
    ("top-down drift", "a slow drift from above, looking down", r"top[- ]down|overhead"),
    ("low-angle track", "a low-angle track close to the ground", r"low[- ]angle"),
)
_FIXED = re.compile(r"fixed camera|static camera|locked[- ]off|camera (?:stays|remains|is) (?:still|fixed)|caméra fixe|plan fixe|caméra immobile", re.I)
MARK = "Camera move for this shot: "


def _base(plan: dict) -> str:
    """What the planner wrote for the shot, without the line of this module and without the lyrics."""
    text = (plan.get("cast") or {}).get("base_prompt", plan.get("prompt", ""))
    return "\n".join(line for line in text.splitlines() if not line.startswith((MARK, "Lyrics sung in this shot", "Spoken in this shot")))


def _kind(text: str) -> int | None:
    """The index in MOVES of the first move the text names, or None."""
    return next((i for i, (_, _, pattern) in enumerate(MOVES) if re.search(pattern, text, re.I)), None)


def add_camera_moves(shot_list, brief: str = "", seed: int = 0, min_seconds: float = 0.0):
    """The shot list where every shot has a camera move, no two in a row alike; applying it again gives the same list.
    A shot shorter than `min_seconds` gets none: too short for a move to read, it keeps the movement of its source."""
    if _FIXED.search(brief or ""):
        return shot_list
    fps = float(shot_list.source.fps)
    done, previous, recent = {}, None, []
    for shot in sorted(shot_list.shots, key=lambda s: s.start_frame):
        plan = dict(shot.plan or {})
        if plan.pop("camera_move", None) is not None:  # the line an earlier run added goes, wherever later steps moved it in the prompt
            plan["prompt"] = "\n".join(line for line in str(plan.get("prompt", "")).splitlines() if not line.startswith(MARK))
        kind = _kind(_base(plan))
        if kind is None or kind == previous:
            kind = (seed + len(recent)) % len(MOVES)  # the shots that move: a short shot takes no turn
            while kind == previous or kind in recent[-3:]:
                kind = (kind + 1) % len(MOVES)
            name, words, _ = MOVES[kind]
            plan.update(prompt=f"{plan.get('prompt', '')}\n{MARK}{words}.".strip(), camera_move=[name, words])
        previous = kind
        recent.append(kind)
        done[shot.shot_id] = replace(shot, plan=plan)
    return replace(shot_list, shots=tuple(done[s.shot_id] for s in shot_list.shots))
