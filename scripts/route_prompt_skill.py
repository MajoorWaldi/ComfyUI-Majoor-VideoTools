"""Let the prompt writer of a shot follow the video model: the Shot sub-graph of the Creative recipes gets a `generator` input that goes to its Edit Skills node,
which swaps the H3 writer for the prompt_skill of the chosen model (generators folder). Run after add_generator_router.py:

    python scripts/route_prompt_skill.py

Idempotent: a recipe whose Shot sub-graph already has the input is skipped."""
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_generator_router import FILES, ROOT, Recipe  # noqa: E402

SHOT_SUB = "Shot"  # the sub-graph "Shot · writes the H3 prompt"
OLD_SENTENCE = " The prompt writer still writes the H3 prompt format for now."
NEW_SENTENCE = (" The prompt of each shot is written by the skill of the model (`seedance_shot_prompt`, `wan_shot_prompt`, `ltx_shot_prompt`; `h3_shot_prompt_from_plan` for H3): "
                "Edit Skills in the Shot sub-graph reads the generator and swaps the writer, so the LLM writes @Image / @Video tags for Seedance and Wan, a single flowing paragraph for LTX.")


def patch(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    r = Recipe(data)
    sub = next(d for d in data["definitions"]["subgraphs"] if d["name"].startswith(SHOT_SUB))
    if any(i["name"] == "generator" for i in sub["inputs"]):
        return False
    instance = next(n for n in data["nodes"] if n["type"] == sub["id"])
    skills = next(n for n in sub["nodes"] if n["type"] == "MajoorEditSkills")
    block = next(g for g in data["groups"] if g["title"].startswith("SHOT_"))
    x0, y0, w, h = block["bounding"]
    getter = next(n for n in data["nodes"] if n["type"] == "GetNode" and n["widgets_values"] == ["GENERATOR"] and x0 <= n["pos"][0] <= x0 + w and y0 <= n["pos"][1] <= y0 + h)

    # inside the sub-graph: the new input of the boundary, one link to Edit Skills
    link_id = sub["state"]["lastLinkId"] + 1
    sub["state"]["lastLinkId"] = link_id
    slot = len(sub["inputs"])
    sub["inputs"].append({"id": str(uuid.uuid5(uuid.UUID(sub["id"]), "generator")), "name": "generator", "type": "STRING", "linkIds": [link_id], "pos": [-200, 20 * slot]})
    sub["inputNode"]["bounding"][3] = max(sub["inputNode"]["bounding"][3], 20 * slot + 50)
    skills["inputs"].append({"name": "generator", "type": "STRING", "link": link_id, "shape": 7})
    sub["links"].append({"id": link_id, "origin_id": -10, "origin_slot": slot, "target_id": skills["id"], "target_slot": len(skills["inputs"]) - 1, "type": "STRING"})

    # outside: the instance reads GENERATOR of the block
    instance["inputs"].append({"name": "generator", "type": "STRING", "link": None})
    r.link(getter, 0, instance, "generator")
    instance["title"] = "SHOT · writes the prompt (the style of the video model)"

    for note in data["nodes"]:
        if note["type"] == "MarkdownNote" and note.get("title") == "GUIDE" and OLD_SENTENCE in note["widgets_values"][0]:
            note["widgets_values"][0] = note["widgets_values"][0].replace(OLD_SENTENCE, NEW_SENTENCE, 1)
            note["size"][1] += 40
    data["last_link_id"] = r.next_link - 1
    text = json.dumps(data, ensure_ascii=False, indent=2).replace("\n", "\r\n")  # the files of the pack: CRLF, no final newline
    for folder in ("recipes", "workflows"):
        (ROOT / folder / path.name).write_bytes(text.encode("utf-8"))
    return True


if __name__ == "__main__":
    for name in FILES:
        print(f"{name}: {'prompt writer routed' if patch(ROOT / 'recipes' / f'{name}.json') else 'already routed'}")
