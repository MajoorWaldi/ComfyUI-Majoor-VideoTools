"""Checks of the plan that a planner (an LLM) wrote, without any model: what an edit asked for must be in the plan. They are the measure of a change of the planner prompt: run the same briefs
before and after, and compare the issues (see scripts/planner_eval.py in the Studio)."""
import json
import re
from fractions import Fraction

from .errors import MajoorError
from .fx import TRANSITION_ALIASES, TRANSITIONS
from .template import _find_shots, _json_text, parse_duration, parse_plan
from .timeline_sources import is_dense_edit

BURST_CUT = 0.26  # seconds: a cut of 3 to 6 frames
NEGATIONS = re.compile(r"\b(no cuts?|no text|no subtitles?|without (cuts|text|subtitles)|one continuous take|single continuous)\b", re.I)


def _seconds(value, fps: Fraction) -> float:
    return float(parse_duration(value, fps)) / float(fps)


def check_plan(text: str, *, duration: float, density: str = "auto", text_allowed: str = "", text_on: bool = True, fps: float = 24.0) -> list[dict]:
    """The issues of a plan, each {"severity": "error" | "warning", "code", "message"}; empty when the plan has what was asked."""
    issues: list[dict] = []

    def add(severity: str, code: str, message: str) -> None:
        issues.append({"severity": severity, "code": code, "message": message})

    try:
        data = _find_shots(json.loads(_json_text(text)))
        shots = [s for s in data["shots"] if isinstance(s, dict)]
    except (json.JSONDecodeError, KeyError, TypeError):
        return [{"severity": "error", "code": "invalid_json", "message": "the plan is not a JSON object with a list of shots"}]
    try:
        parsed = parse_plan(text, fps, "9:16", 320)
    except MajoorError as error:
        add("error", "schema", str(error)[:200])
        return issues
    rate = Fraction(str(fps)).limit_denominator(1001)
    lengths = []
    for shot in shots:
        subs = [c for c in shot.get("sub_cuts", []) if isinstance(c, dict)]
        lengths.append(_seconds(shot["duration"], rate) if "duration" in shot else sum(_seconds(c["duration"], rate) for c in subs))
    total = sum(lengths)
    if abs(total - duration) > max(0.5, 0.05 * duration):
        add("error", "duration", f"the shots add up to {total:.1f} s, {duration:g} s were asked")
    if duration >= 8 and len(shots) < 3:
        add("warning", "shots", f"{len(shots)} shot(s) for {duration:g} s")
    for i, shot in enumerate(shots):
        subs = [c for c in shot.get("sub_cuts", []) if isinstance(c, dict) and "duration" in c]
        if subs and "duration" in shot and abs(sum(_seconds(c["duration"], rate) for c in subs) - lengths[i]) > 0.06:
            add("warning", "sub_cuts_sum", f"{shot.get('id', i + 1)}: the sub-cuts do not add up to the shot")
        prompt = str(shot.get("prompt", ""))
        if len(prompt) < 20:
            add("error", "prompt", f"{shot.get('id', i + 1)}: no usable prompt")
        contradicts_cuts = bool(subs) or density in ("medium", "high")
        contradicts_text = text_on and bool(text_allowed.strip())
        conflicts = []
        for match in NEGATIONS.finditer(prompt):
            words = match.group(0).lower()
            concerns_text = "text" in words or "subtitle" in words
            conflicts.append(contradicts_text if concerns_text else contradicts_cuts)
        if any(conflicts):
            add("warning", "negation", f"{shot.get('id', i + 1)}: the prompt carries a negation that contradicts the cuts")
        transition = shot.get("transition")
        name = transition.get("type") if isinstance(transition, dict) else transition
        if isinstance(name, str) and name not in TRANSITIONS and name not in TRANSITION_ALIASES:
            add("warning", "transition", f"{shot.get('id', i + 1)}: unknown transition '{name}'")
    bursts = [s for s in shots if len([c for c in s.get("sub_cuts", []) if isinstance(c, dict) and "duration" in c and 3 <= parse_duration(c["duration"], rate) <= 6]) >= 3]
    with_cuts = [s for s in shots if s.get("sub_cuts")]
    if density == "high" and not bursts and not is_dense_edit(shots,float(rate)):
        add("error", "burst", "cut density high: no shot has a burst of 3 or more cuts of 3 to 6 frames")
    elif density == "medium" and not with_cuts:
        add("warning", "sub_cuts", "cut density medium: no shot has sub-cuts")
    elif density == "low" and with_cuts:
        add("warning", "sub_cuts", "cut density low: the plan has sub-cuts")
    texts = []
    for shot in shots:
        text = shot.get("text") or (shot.get("fx") or {}).get("text")
        if text:
            texts.append((shot.get("id", "?"), text))
        texts.extend((shot.get("id", "?"), layer) for layer in shot.get("motion", []) if isinstance(layer, dict) and layer.get("type", "text") == "text" and layer.get("content"))
    contents = [str((t if isinstance(t, dict) else {"content": t}).get("content", "")).strip() for _, t in texts]
    if not text_on and texts:
        add("error", "text_off", "the plan has a text although the text is off")
    if text_on and text_allowed.strip():
        found = [c for c in contents if c.lower() == text_allowed.strip().lower()]
        if len(found) != 1:
            add("error", "text_allowed", f"'{text_allowed.strip()}' should be on the screen once, it is there {len(found)} time(s)")
        if any(c.lower() != text_allowed.strip().lower() for c in contents):
            add("error", "text_invented", "the plan contains words outside the authorized text")
    elif texts and text_on:
        add("warning", "text_invented", "the plan has a text that the user did not give")
    if len(texts) > 3:
        add("warning", "text_count", f"{len(texts)} texts, 3 at most")
    for content in contents:
        if len(content.split()) > 3 and content.lower() != text_allowed.strip().lower():
            add("warning", "text_length", f"'{content}' is longer than 3 words")
    from .story import story_issues
    for code, message in story_issues(parsed.shots):
        add('warning', code, message)
    for shot in shots:
        if (shot.get('story') or {}).get('protect_action') is True and len(shot.get('sub_cuts') or []) > 1:
            add('warning', 'protected_action', f"{shot.get('id', '?')}: essential action has sub-cuts")
    return issues


def summarize(issues: list[dict]) -> dict:
    return {"errors": sum(i["severity"] == "error" for i in issues), "warnings": sum(i["severity"] == "warning" for i in issues), "codes": sorted({i["code"] for i in issues})}
