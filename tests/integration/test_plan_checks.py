"""The checks of a plan that a planner wrote, and the briefs that measure a planner."""
import json
from pathlib import Path

from majoor_videotools.core.plan_checks import check_plan, summarize

PROMPT = "A close-up of the glass perfume bottle on wet black stone, rim light along its edge, a slow push-in."


def plan(shots):
    return json.dumps({"fps": 24, "aspect_ratio": "9:16", "shots": shots})


def good():
    return [
        {"id": "SHOT_001", "duration": 2.0, "prompt": PROMPT},
        {"id": "SHOT_002", "duration": 3.0, "prompt": PROMPT, "transition": "whip"},
        {"id": "SHOT_003", "duration": 3.0, "prompt": PROMPT, "sub_cuts": [{"duration": 0.17}, {"duration": 0.17}, {"duration": 0.17}, {"duration": 0.17}, {"duration": 2.32}]},
        {"id": "SHOT_004", "duration": 4.0, "prompt": PROMPT},
        {"id": "SHOT_005", "duration": 3.0, "prompt": PROMPT, "text": {"content": "NEW DROP"}},
    ]


def codes(text, **asked):
    return {i["code"] for i in check_plan(text, **{"duration": 15, **asked})}


def test_a_plan_with_what_was_asked_has_no_issue():
    assert check_plan(plan(good()), duration=15, density="high", text_allowed="NEW DROP") == []
    assert summarize([]) == {"errors": 0, "warnings": 0, "codes": []}


def test_the_plan_must_be_json_with_the_right_length():
    assert codes("not json") == {"invalid_json"}
    assert "duration" in codes(plan(good()), duration=30)
    assert "shots" in codes(plan([{"id": "SHOT_001", "duration": 15, "prompt": PROMPT}]))


def test_a_high_cut_density_needs_its_burst_and_a_low_one_has_none():
    calm = [dict(s) for s in good()]
    for s in calm:
        s.pop("sub_cuts", None)
    assert "burst" in codes(plan(calm), density="high", text_allowed="NEW DROP")
    assert "sub_cuts" in codes(plan(calm), density="medium", text_allowed="NEW DROP")
    assert "sub_cuts" in codes(plan(good()), density="low", text_allowed="NEW DROP")
    assert "burst" not in codes(plan(good()), density="high", text_allowed="NEW DROP")


def test_the_words_asked_for_are_on_the_screen_once_and_no_other_text_is_invented():
    without = [dict(s) for s in good()]
    without[-1].pop("text")
    assert "text_allowed" in codes(plan(without), text_allowed="NEW DROP")
    twice = [dict(s) for s in good()]
    twice[0]["text"] = {"content": "NEW DROP"}
    assert "text_allowed" in codes(plan(twice), text_allowed="NEW DROP")
    assert "text_invented" in codes(plan(good()), text_allowed="")
    assert "text_off" in codes(plan(good()), text_allowed="NEW DROP", text_on=False)
    long = [dict(s) for s in good()]
    long[0]["text"] = {"content": "A VERY LONG LINE OF WORDS"}
    assert "text_length" in codes(plan(long), text_allowed="NEW DROP")


def test_a_prompt_that_contradicts_the_cuts_is_reported():
    bad = [dict(s) for s in good()]
    bad[1]["prompt"] = "One continuous take of the bottle, no cuts, no text, slow push-in on the glass."
    bad[2]["transition"] = "teleport"
    found = codes(plan(bad), text_allowed="NEW DROP")
    assert "negation" in found and "transition" in found


def test_the_briefs_that_measure_a_planner_are_complete():
    briefs = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "planner_briefs.json").read_text(encoding="utf-8"))
    assert len(briefs) == 10 and len({b["id"] for b in briefs}) == 10
    assert {b["cut_density"] for b in briefs} == {"auto", "low", "medium", "high"}
    for b in briefs:
        assert b["brief"] and 8 <= b["duration"] <= 30 and b["style"], b["id"]


def test_the_planner_report_counts_the_issues_of_each_brief(tmp_path):
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[2] / "HyperKut Studio" / "scripts" / "planner_eval.py"
    spec = importlib.util.spec_from_file_location("planner_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    briefs = json.loads(module.BRIEFS.read_text(encoding="utf-8"))
    perfume = next(b for b in briefs if b["id"] == "perfume-drop")
    calm = [dict(s) for s in good()]
    for s in calm:
        s.pop("sub_cuts", None)
    report = module.evaluate([perfume], {"perfume-drop": [plan(good()), plan(calm)]})
    assert report[0]["runs"] == 2 and report[0]["errors"] == 1 and report[0]["codes"] == ["burst"]
    assert module.evaluate([perfume], {})[0]["runs"] == 0
    folder = tmp_path / "plans"
    folder.mkdir()
    (folder / "perfume-drop.1.json").write_text(plan(good()), encoding="utf-8")
    old = sys.argv
    sys.argv = ["planner_eval.py", "--plans", str(folder), "--only", "perfume-drop"]
    try:
        assert module.main() == 0
    finally:
        sys.argv = old
    assert json.loads((module.APP / "workspace" / "planner_eval.json").read_text(encoding="utf-8"))[0]["errors"] == 0
