"""Give the VIDEO MODEL control of the Creative recipes its budget (MAX API SECONDS) and say so in the GUIDE. Run after add_generator_router.py:

    python scripts/add_cost_guard.py

Idempotent: a Generator Select that already has the widget is skipped."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_generator_router import FILES, ROOT, Recipe, push_notes_down  # noqa: E402

BUDGET = 120
AFTER = " The prompt of each shot is written by the skill"
SENTENCE = (f" **Budget**: MAX API SECONDS on VIDEO MODEL ({BUDGET} by default, 0 = no limit) caps the seconds of video asked for from an API model in one run, retries included. "
            "Deploy Shots writes the estimate of the whole edit in its report and asks before a deployment that would go over; Generate Shot (API) stops before the take that would pass it, without calling the model.")


def patch(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    r = Recipe(data)
    select = next(n for n in data["nodes"] if n["type"] == "MajoorGeneratorSelect")
    if any(i["name"] == "max_api_seconds" for i in select["inputs"]):
        return False
    select["inputs"].append({"name": "max_api_seconds", "type": "INT", "shape": 7, "widget": {"name": "max_api_seconds"}, "link": None})
    select["widgets_values"] = [select["widgets_values"][0], BUDGET]
    select["widgets_values_named"] = {"generator": select["widgets_values"][0], "max_api_seconds": BUDGET}
    sizes = {n["id"]: n["size"][1] for n in data["nodes"] if n["type"] == "MarkdownNote"}
    for note in data["nodes"]:
        if note["type"] == "MarkdownNote" and note.get("title") == "GUIDE" and AFTER in note["widgets_values"][0]:
            note["widgets_values"][0] = note["widgets_values"][0].replace(AFTER, SENTENCE + AFTER, 1)
            note["size"][1] += 60
    push_notes_down(r, sizes)
    text = json.dumps(data, ensure_ascii=False, indent=2).replace("\n", "\r\n")  # the files of the pack: CRLF, no final newline
    for folder in ("recipes", "workflows"):
        (ROOT / folder / path.name).write_bytes(text.encode("utf-8"))
    return True


if __name__ == "__main__":
    for name in FILES:
        print(f"{name}: {'budget added' if patch(ROOT / 'recipes' / f'{name}.json') else 'already has it'}")
