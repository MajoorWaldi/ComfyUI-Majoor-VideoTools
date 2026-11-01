"""Character casting: the JSON of the casting_planner skill (one prompt, several characters), checked, and
spread over the shots of a timeline. No model, no network, no GPU.

A casting is {"style": str, "shot_sizes": [..], "characters": [{"id","name","look","location","start","end","performance"}]}.
`start` and `end` are the seconds of the timeline this character performs. The bible text is what every shot
prompt of that character repeats, so the identity stays the same from one take to the next."""
import json
import re
from dataclasses import replace

from .creative_director import choose_sizes
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
    if isinstance(sizes, str) and sizes.strip().lower() == "auto":
        sizes = "auto"  # the Creative Director chooses each size from the duration, the energy and the place of the shot
    else:
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


MAX_REFERENCES = 5


def parse_references(text, casting: dict) -> dict[str, list[str]]:
    """The reference pictures of each character: {"id": "file.png"} or {"id": ["a.png", "b.png"]}. These are names of pictures the workflow loads (never paths).

    A picture is tied to a character of the casting, at most five per character; an unknown character or a path is an error, so a typo cannot silently drop an identity."""
    if text is None or (isinstance(text, str) and not text.strip()):
        return {}
    try:
        data = json.loads(text) if isinstance(text, str) else text
    except ValueError as error:
        raise MajoorError("The character references are not valid JSON") from error
    if not isinstance(data, dict):
        raise MajoorError("The character references must be an object {character id: picture or list of pictures}")
    known = {c["id"] for c in casting["characters"]}
    references = {}
    for cid, value in data.items():
        if cid not in known:
            raise MajoorError(f"References name '{cid}', which is not a character of the casting ({sorted(known)})")
        names = [value] if isinstance(value, str) else value
        if not isinstance(names, list) or not names or len(names) > MAX_REFERENCES:
            raise MajoorError(f"References of '{cid}': give one picture or a list of 1 to {MAX_REFERENCES}")
        for name in names:
            if not isinstance(name, str) or not name.strip() or name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/") or ":" in name[:3]:
                raise MajoorError(f"References of '{cid}': '{name}' is not a picture name (no path, no '..')")
        references[cid] = [n.strip() for n in names]
    return references


def sheet_prompt(casting: dict, character_id: str) -> str:
    """The prompt that makes the reference picture of a character once, to be reused by every shot: neutral, evenly lit, identity only."""
    character = next((c for c in casting["characters"] if c["id"] == character_id), None)
    if character is None:
        raise MajoorError(f"Casting has no character '{character_id}'")
    shared = f" {casting['style']}." if casting["style"] else ""
    return (f"Character reference of {character['name']}: {character['look']}.{shared} "
            "Full figure, facing the camera, relaxed pose, plain neutral background, even soft light, sharp details of face, hands and clothes. No text, no props.")


def cast_shots(casting: dict, shots, fps: float, energies: dict | None = None) -> dict[str, dict]:
    """{shot_id: {"character_id","location","shot_size","performance"}} for the shots of a timeline.

    A shot belongs to the character whose seconds hold its middle; a shot between two parts goes to the nearest one.
    Shot sizes alternate in the order of the casting inside each character, so cuts alternate medium and close-up."""
    sizes, used, result, owned = casting["shot_sizes"], {}, {}, {}
    shots = list(shots)
    for shot in shots:
        middle = (shot.start_frame + shot.end_frame_exclusive) / 2 / fps
        character = min(casting["characters"], key=lambda c: 0 if c["start"] <= middle < c["end"] else min(abs(middle - c["start"]), abs(middle - c["end"])))
        n = used[character["id"]] = used.get(character["id"], -1) + 1
        owned.setdefault(character["id"], []).append({"id": shot.shot_id, "duration": (shot.end_frame_exclusive - shot.start_frame) / fps,
                                                      "energy": (energies or {}).get(shot.shot_id)})
        result[shot.shot_id] = {"character_id": character["id"], "location": character["location"],
                                "shot_size": sizes[n % len(sizes)] if sizes != "auto" else "medium", "performance": character["performance"]}
    if sizes == "auto":
        opening = shots[0].shot_id if shots else None
        for rows in owned.values():
            for shot_id, size in choose_sizes(rows, first_of_edit=opening).items():
                result[shot_id]["shot_size"] = size
    return result


def apply_casting(shot_list, casting: dict, references: dict | None = None, energies: dict | None = None):
    """The shot list with the cast written in each plan: `location`, `cast`, and the bible, shot size and performance in front of the prompt.

    Applying a casting again replaces the earlier one, because the original prompt is kept in `cast.base_prompt`."""
    cast = cast_shots(casting, shot_list.shots, float(shot_list.source.fps), energies)
    shots = []
    for shot in shot_list.shots:
        plan, row = dict(shot.plan or {}), cast[shot.shot_id]
        base = plan.get("cast", {}).get("base_prompt", plan.get("prompt", ""))
        head = [bible_text(casting, row["character_id"]), f"Shot size: {row['shot_size'].replace('_', ' ')}."]
        if row["performance"]:
            head.append(f"Performance: {row['performance']}")
        refs = list((references or {}).get(row["character_id"], []))
        plan.update(prompt="\n".join([*head, base]).strip(), cast={**row, "base_prompt": base, **({"references": refs} if refs else {})})
        if row["location"]:
            plan["location"] = row["location"]
        shots.append(replace(shot, plan=plan))
    return replace(shot_list, shots=tuple(shots))
