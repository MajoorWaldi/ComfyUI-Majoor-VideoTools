"""Character casting: the JSON of the casting_planner skill (one prompt, several characters), checked, and
spread over the shots of a timeline. No model, no network, no GPU.

A casting is {"style": str, "shot_sizes": [..], "characters": [{"id","name","look","location","start","end","performance"}]}.
`start` and `end` are the seconds of the timeline this character performs. The bible text is what every shot
prompt of that character repeats, so the identity stays the same from one take to the next."""
import json
import re
from dataclasses import replace

from .errors import MajoorError

MAX_CHARACTERS = 12
SHOT_SIZES = ("wide", "medium", "close_up", "extreme_close_up")
_ID = re.compile(r"^[a-z0-9_]{1,32}$")


def _text(value, name, *, required=True):
    if not isinstance(value, str) or (required and not value.strip()):
        raise MajoorError(f"Casting: {name} must be {'non-empty ' if required else ''}text")
    return value.strip()


def parse_casting(text: str) -> dict:
    raw = text.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:-1])
    try:
        start = raw.find("{")
        data = json.JSONDecoder().raw_decode(raw[start:] if start >= 0 else raw)[0]
    except (ValueError, TypeError) as error:
        raise MajoorError("The casting planner did not return valid JSON") from error
    if not isinstance(data, dict) or not isinstance(data.get("characters"), list) or not data["characters"]:
        raise MajoorError("Casting needs a non-empty list of characters")
    data["characters"] = data["characters"][:MAX_CHARACTERS]  # the first twelve
    sizes = data.get("shot_sizes", ["medium", "close_up"])
    sizes = [str(s).strip().lower().replace(" ", "_").replace("-", "_") for s in sizes] if isinstance(sizes, list) else []
    sizes = [s for s in sizes if s in SHOT_SIZES] or ["medium", "close_up"]  # a size that does not exist is left out
    characters, seen = [], set()
    for item in data["characters"]:
        if not isinstance(item, dict):
            raise MajoorError("Each casting character must be an object")
        name = _text(item.get("name", item.get("id")), "character name")
        base = re.sub(r"[^a-z0-9_]+", "_", str(item.get("id") or name).strip().lower()).strip("_")[:28] or "character"
        cid, n = base, 1
        while cid in seen:  # the same id twice: the second gets a number
            n += 1
            cid = f"{base}_{n}"
        seen.add(cid)
        start, end = item.get("start"), item.get("end")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (start, end)):
            raise MajoorError(f"Casting: {cid} needs numbers for start and end (seconds)")
        start, end = sorted((max(start, 0), max(end, 0)))  # a part written backwards is the same part
        if end == start:
            raise MajoorError(f"Casting: {cid} needs a part that lasts (start < end)")
        characters.append({"id": cid, "name": name, "look": _text(item.get("look", name), f"{cid}.look"),
                           "location": _text(item.get("location", ""), f"{cid}.location", required=False),
                           "performance": _text(item.get("performance", ""), f"{cid}.performance", required=False),
                           "start": float(start), "end": float(end)})
    return {"style": _text(data.get("style", ""), "style", required=False), "shot_sizes": sizes, "characters": characters}


def bible_text(casting: dict, character_id: str) -> str:
    """The identity block a shot prompt of this character starts from."""
    character = next((c for c in casting["characters"] if c["id"] == character_id), None)
    if character is None:
        raise MajoorError(f"Casting has no character '{character_id}'")
    lines = [f"{character['name']}: {character['look']}"]
    if casting["style"]:
        lines.append(f"Shared look: {casting['style']}")
    if character["location"]:
        lines.append(f"Location: {character['location']}")
    return "\n".join(lines)


def cast_shots(casting: dict, shots, fps: float) -> dict[str, dict]:
    """{shot_id: {"character_id","location","shot_size","performance"}} for the shots of a timeline.

    A shot belongs to the character whose seconds hold its middle; a shot between two parts goes to the nearest one.
    Shot sizes alternate in the order of the casting inside each character, so cuts alternate medium and close-up."""
    sizes, used, result = casting["shot_sizes"], {}, {}
    for shot in shots:
        middle = (shot.start_frame + shot.end_frame_exclusive) / 2 / fps
        character = min(casting["characters"], key=lambda c: 0 if c["start"] <= middle < c["end"] else min(abs(middle - c["start"]), abs(middle - c["end"])))
        n = used[character["id"]] = used.get(character["id"], -1) + 1
        result[shot.shot_id] = {"character_id": character["id"], "location": character["location"],
                                "shot_size": sizes[n % len(sizes)], "performance": character["performance"]}
    return result


def apply_casting(shot_list, casting: dict):
    """The shot list with the cast written in each plan: `location`, `cast`, and the bible, shot size and performance in front of the prompt.

    Applying a casting again replaces the earlier one, because the original prompt is kept in `cast.base_prompt`."""
    cast = cast_shots(casting, shot_list.shots, float(shot_list.source.fps))
    shots = []
    for shot in shot_list.shots:
        plan, row = dict(shot.plan or {}), cast[shot.shot_id]
        base = plan.get("cast", {}).get("base_prompt", plan.get("prompt", ""))
        head = [bible_text(casting, row["character_id"]), f"Shot size: {row['shot_size'].replace('_', ' ')}."]
        if row["performance"]:
            head.append(f"Performance: {row['performance']}")
        plan.update(prompt="\n".join([*head, base]).strip(), cast={**row, "base_prompt": base})
        if row["location"]:
            plan["location"] = row["location"]
        shots.append(replace(shot, plan=plan))
    return replace(shot_list, shots=tuple(shots))
