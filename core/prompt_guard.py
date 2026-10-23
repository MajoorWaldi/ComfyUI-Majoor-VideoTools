"""Generation prompts keep the role, the cuts and the transitions of a shot, but never negate them.

"One continuous take, no cuts, no text." contradicts the sub-cuts of a shot, and a generator reading "no text" or "no cuts" can behave worse
than one that reads nothing. A language model writes it by habit, so it is removed from the prompts of a plan whatever the model wrote.
Only the negations go: every positive description of cuts, transitions or framing stays."""
import json
import re

NEGATION = re.compile(
    r"\b(?:no|without)\s+(?:any\s+)?(?:visible\s+)?(?:jump\s+)?(?:cuts?|text|texts|subtitles?|captions?|logos?|titles?|watermarks?|montage|transitions?)\b"
    r"|\b(?:one|a single|single)\s+(?:continuous|uninterrupted|unbroken)\s+(?:take|shot)\b"
    r"|\bcontinuous take\b",
    re.IGNORECASE,
)
SENTENCE = re.compile(r"(?<=[.!?])\s+")
CLAUSE = re.compile(r"(?<=[,;])\s+")


def _tidy(text: str) -> str:
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip(" ,;")


def strip_negations(text: str) -> tuple[str, list[str]]:
    """The text without the clauses that negate cuts, text, transitions or the like. Returns (text, removed clauses). Lines are kept."""
    removed: list[str] = []
    lines = []
    for line in str(text or "").split("\n"):
        sentences = []
        for sentence in SENTENCE.split(line):
            if not NEGATION.search(sentence):
                sentences.append(sentence)
                continue
            kept = []
            for clause in CLAUSE.split(sentence):
                if NEGATION.search(clause):
                    removed.append(clause.strip(" .,;"))
                else:
                    kept.append(clause)
            rebuilt = _tidy(" ".join(kept))
            if re.search(r"\w", rebuilt):
                sentences.append(rebuilt + ("" if rebuilt[-1] in ".!?:" else "."))
        lines.append(" ".join(sentences))
    return "\n".join(lines).strip() if "\n" not in str(text or "") else "\n".join(lines).strip(), removed


def clean_plan_text(plan_text: str) -> tuple[str, list[str]]:
    """The same for the `prompt` and `image_prompt` of every shot of a plan written as JSON. Returns (plan JSON, removed clauses)."""
    from .template import _find_shots, _json_text  # the plan readers

    try:
        data = _find_shots(json.loads(_json_text(plan_text)))
    except json.JSONDecodeError:
        return plan_text, []  # parse_plan reports it
    removed: list[str] = []
    for shot in data.get("shots", []) if isinstance(data, dict) else []:
        if not isinstance(shot, dict):
            continue
        for key in ("prompt", "image_prompt", "video_prompt", "location"):
            if isinstance(shot.get(key), str):
                shot[key], gone = strip_negations(shot[key])
                removed += gone
    return json.dumps(data), removed
