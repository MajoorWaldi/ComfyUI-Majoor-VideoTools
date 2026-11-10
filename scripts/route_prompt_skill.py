"""Let the prompt writer of a shot follow the video model: the Shot sub-graph of the Creative recipes gets a `generator` input that goes to its Edit Skills node,
which swaps the H3 writer for the prompt_skill of the chosen model (generators folder). Run after add_generator_router.py:

    python scripts/route_prompt_skill.py

Idempotent: a recipe whose Shot sub-graph already has the input is skipped."""
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_generator_router import FILES, ROOT, Recipe, write_like  # noqa: E402

WRITERS = ("h3_shot_prompt_from_plan", "remix_shot_prompt")  # the skills of the shot writers: the Edit Skills node that has one is the one that follows the model
OLD_SENTENCE = " The prompt writer still writes the H3 prompt format for now."
NEW_SENTENCE_REMIX = (" The prompt of each shot is written by the skill of the model (`seedance_remix_prompt` for the edit mode of Seedance, `remix_shot_prompt` for H3): "
                     "Edit Skills in the ANALYSIS sub-graph reads the generator and swaps the writer.")
NEW_SENTENCE = (" The prompt of each shot is written by the skill of the model (`seedance_shot_prompt`, `wan_shot_prompt`, `ltx_shot_prompt`; `h3_shot_prompt_from_plan` for H3): "
                "Edit Skills in the Shot sub-graph reads the generator and swaps the writer, so the LLM writes @Image / @Video tags for Seedance and Wan, a single flowing paragraph for LTX.")


def patch(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    r = Recipe(data)
    sub, skills = next((d, n) for d in data["definitions"]["subgraphs"] for n in d["nodes"] if n["type"] == "MajoorEditSkills" and (n.get("widgets_values") or [""])[0] in WRITERS)
    if any(i["name"] == "generator" for i in sub["inputs"]):
        return False
    remix = (skills["widgets_values"] or [""])[0] == "remix_shot_prompt"
    instance = next(n for n in data["nodes"] if n["type"] == sub["id"])
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
    if not remix:
        instance["title"] = "SHOT · writes the prompt (the style of the video model)"

    for note in data["nodes"]:
        if note["type"] == "MarkdownNote" and note.get("title") == "GUIDE" and OLD_SENTENCE in note["widgets_values"][0]:
            note["widgets_values"][0] = note["widgets_values"][0].replace(OLD_SENTENCE, NEW_SENTENCE, 1)
            note["size"][1] += 40
        elif remix and note["type"] == "MarkdownNote" and note.get("title") == "GUIDE" and "Optional loaders are bypassed" in note["widgets_values"][0]:
            note["widgets_values"][0] = note["widgets_values"][0].replace("Optional loaders are bypassed", NEW_SENTENCE_REMIX.lstrip() + "\n" + "Optional loaders are bypassed", 1)
            note["size"][1] += 40
    data["last_link_id"] = r.next_link - 1
    write_like(path, data)
    return True


if __name__ == "__main__":
    for name in FILES:
        print(f"{name}: {'prompt writer routed' if patch(ROOT / 'recipes' / f'{name}.json') else 'already routed'}")
