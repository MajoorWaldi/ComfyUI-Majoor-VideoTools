"""Give the VIDEO MODEL control of the Creative recipes its budgets (MAX API SECONDS and MAX API USD) and say so in the GUIDE. Run after add_generator_router.py:

    python scripts/add_cost_guard.py

Idempotent: a Generator Select that already has both widgets is skipped."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_generator_router import FILES, ROOT, Recipe, push_notes_down  # noqa: E402

SECONDS, USD = 120, 0.0
AFTER = " The prompt of each shot is written by the skill"
SENTENCE = (f" **Budget**: MAX API SECONDS ({SECONDS} by default) and MAX API USD (0 = no limit) on VIDEO MODEL cap what one run asks from an API model, retries included; 0 removes a cap. "
            "The dollars are the price badges of the API nodes added up (needs `jsonata-python`, see requirements.txt). "
            "Deploy Shots writes the estimate of the whole edit in its report and asks before a deployment that would go over; Generate Shot (API) stops before the take that would pass a budget, without calling the model.")
OLD_SENTENCE = (f" **Budget**: MAX API SECONDS on VIDEO MODEL ({SECONDS} by default, 0 = no limit) caps the seconds of video asked for from an API model in one run, retries included. "
                "Deploy Shots writes the estimate of the whole edit in its report and asks before a deployment that would go over; Generate Shot (API) stops before the take that would pass it, without calling the model.")


def patch(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    r = Recipe(data)
    select = next(n for n in data["nodes"] if n["type"] == "MajoorGeneratorSelect")
    names = [i["name"] for i in select["inputs"]]
    if "max_api_seconds" in names and "max_api_usd" in names:
        return False
    if "max_api_seconds" not in names:
        select["inputs"].append({"name": "max_api_seconds", "type": "INT", "shape": 7, "widget": {"name": "max_api_seconds"}, "link": None})
    select["inputs"].append({"name": "max_api_usd", "type": "FLOAT", "shape": 7, "widget": {"name": "max_api_usd"}, "link": None})
    generator = select["widgets_values"][0]
    select["widgets_values"] = [generator, SECONDS, USD]
    select["widgets_values_named"] = {"generator": generator, "max_api_seconds": SECONDS, "max_api_usd": USD}
    sizes = {n["id"]: n["size"][1] for n in data["nodes"] if n["type"] == "MarkdownNote"}
    for note in data["nodes"]:
        if note["type"] == "MarkdownNote" and note.get("title") == "GUIDE":
            text = note["widgets_values"][0]
            if OLD_SENTENCE in text:
                note["widgets_values"][0] = text.replace(OLD_SENTENCE, SENTENCE, 1)
                note["size"][1] += 40
            elif AFTER in text and SENTENCE not in text:
                note["widgets_values"][0] = text.replace(AFTER, SENTENCE + AFTER, 1)
                note["size"][1] += 100
    push_notes_down(r, sizes)
    text = json.dumps(data, ensure_ascii=False, indent=2).replace("\n", "\r\n")  # the files of the pack: CRLF, no final newline
    for folder in ("recipes", "workflows"):
        (ROOT / folder / path.name).write_bytes(text.encode("utf-8"))
    return True


if __name__ == "__main__":
    for name in FILES:
        print(f"{name}: {'budgets added' if patch(ROOT / 'recipes' / f'{name}.json') else 'already has them'}")
