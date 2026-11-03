"""The plan of a remix laid on the shots found in the source: the story each shot tells, who it shows, where, and whether it is generated, kept or replaced by a title.

The cuts, the order and the durations of the source never change: a shot the planner does not name is left as it is, and an id it invents is ignored."""
import json
import re
from dataclasses import replace

from .errors import MajoorError

SOURCES = ("generate", "original", "title")
MAX_TEXT = 600


def _clean(value, limit=MAX_TEXT) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit] if isinstance(value, str) else ""


def parse_remix_plan(text: str, pictures: int = 5) -> dict:
    """{"story", "characters": [{id, name, picture, look}], "shots": {SHOT_ID: {...}}} from the answer of the remix planner. Raises MajoorError when no JSON object is found.

    `pictures`: how many reference pictures there are; a person given a picture that does not exist is described by its look instead."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:-1])
    try:
        start = raw.find("{")
        data = json.JSONDecoder().raw_decode(raw[start:] if start >= 0 else raw)[0]
    except (ValueError, TypeError) as error:
        raise MajoorError("The remix planner did not return valid JSON") from error
    if not isinstance(data, dict):
        raise MajoorError("The remix plan must be a JSON object")
    characters, seen = [], set()
    for item in data.get("characters") or []:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name") or item.get("id"), 60)
        cid = re.sub(r"[^a-z0-9_]+", "_", str(item.get("id") or name).lower()).strip("_")[:28]
        if not cid or cid in seen:
            continue
        seen.add(cid)
        picture = item.get("picture", 0)
        picture = picture if isinstance(picture, int) and not isinstance(picture, bool) and 0 <= picture <= min(pictures, 5) else 0
        characters.append({"id": cid, "name": name or cid, "picture": picture, "look": _clean(item.get("look"), 300)})
    shots = {}
    rows = data.get("shots") or []
    if isinstance(rows, dict):  # {"SHOT_001": {...}} is the same plan
        rows = [{**row, "id": key} for key, row in rows.items() if isinstance(row, dict)]
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("id", "")).strip().upper()
        if not sid:
            continue
        source = str(row.get("source", "generate")).strip().lower()
        shots[sid] = {"source": source if source in SOURCES else "generate", "prompt": _clean(row.get("prompt")),
                      "shows": _clean(row.get("shows")), "location": _clean(row.get("location"), 200),
                      "cast": re.sub(r"[^a-z0-9_]+", "_", str(row.get("cast") or "").lower()).strip("_"),
                      "title": _clean(row.get("title_text") or row.get("title"), 80)}
    return {"story": _clean(data.get("story"), 1500), "characters": characters, "shots": shots}


def apply_remix_plan(shot_list, plan: dict, *, cast=True, places=True, keep_sources=True):
    """The shot list with the plan written in each shot it names; applying a plan again replaces the earlier one."""
    characters = {c["id"]: c for c in plan["characters"]}
    shots = []
    for shot in shot_list.shots:
        row = plan["shots"].get(shot.shot_id.upper())
        current = dict(shot.plan or {})
        base = (current.pop("remix", None) or {}).get("base_prompt", current.get("prompt", ""))
        for key in ("cast", "location", "render_source"):
            if (current.get("remix_set") or {}).get(key):
                current.pop(key, None)
        current.pop("remix_set", None)
        if row is None:
            shots.append(replace(shot, plan={**current, "prompt": base} if current or base else shot.plan))
            continue
        lines, written = [], {}
        who = characters.get(row["cast"]) if cast else None
        if who:
            if who["picture"]:
                lines.append(f"Who: the person of <Picture {who['picture']}> ({who['name']}) takes the place of the person the source shows.")
            elif who["look"]:
                lines.append(f"Who: {who['name']}, {who['look']}")
            current["cast"] = {"character_id": who["id"], "name": who["name"], "picture": who["picture"]}
            written["cast"] = True
        if places and row["location"]:
            lines.append(f"Place: {row['location']}.")
            current["location"] = row["location"]
            written["location"] = True
        if row["prompt"]:
            lines.append(row["prompt"])
        if keep_sources and row["source"] == "original":
            current["render_source"] = {"kind": "original"}
            written["render_source"] = True
        elif keep_sources and row["source"] == "title" and row["title"]:
            current["render_source"] = {"kind": "graphic", "text": row["title"], "color": "#101018"}
            written["render_source"] = True
        current.update(prompt="\n".join([*lines, base]).strip(), remix={"base_prompt": base, "shows": row["shows"]}, remix_set=written)
        shots.append(replace(shot, plan=current))
    return replace(shot_list, shots=tuple(shots))


def plan_summary(plan: dict, shot_list) -> str:
    """The story and what each shot becomes, in words, for the later steps and the person who reads the node."""
    lines = [f"STORY OF THE REMIX: {plan['story']}"] if plan["story"] else []
    fps = float(shot_list.source.fps)
    for shot in shot_list.shots:
        row = plan["shots"].get(shot.shot_id.upper())
        if row:
            seconds = f"{shot.start_frame / fps:.1f}-{shot.end_frame_exclusive / fps:.1f} s"
            what = {"original": "kept as in the source", "title": f'title card "{row["title"]}"'}.get(row["source"], row["prompt"] or "generated")
            lines.append(f"{shot.shot_id} ({seconds}): {what}" + (f" [shows: {row['shows']}]" if row["shows"] else ""))
    return "\n".join(lines)
