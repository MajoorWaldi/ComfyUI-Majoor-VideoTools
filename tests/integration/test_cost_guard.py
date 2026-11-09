import json
import pytest

from majoor_videotools.core import deploy as dp
from majoor_videotools.core.cost_guard import DEFAULT_BUDGET_SECONDS, Choice, Ledger, deploy_notes, estimate, selected_generator
from majoor_videotools.core.generators import load_generator

SHOTS = [("SHOT_001", 72), ("SHOT_002", 130), ("SHOT_003", 48)]  # 3 s, 5.4 s, 2 s at 24 fps


def _workflow(generator, budget=None):
    node = {"type": "MajoorGeneratorSelect", "widgets_values": [generator] + ([] if budget is None else [budget])}
    if budget is not None:
        node["widgets_values_named"] = {"generator": generator, "max_api_seconds": budget}
    return {"nodes": [node]}


def test_the_estimate_counts_the_seconds_the_model_will_be_asked_for():
    e = estimate("seedance_2_5", [f for _, f in SHOTS], 24, 120)
    assert e.paid and e.shots == 3 and e.seconds == 4 + 6 + 4  # the model starts at 4 s, rounds up to whole seconds
    assert e.stops_at is None and "Within the budget of 120 s" in e.text and e.price is None  # outside ComfyUI no badge is known: seconds only
    assert not estimate("minimax_h3", [72], 24).paid and "nothing to pay" in estimate("minimax_h3", [72], 24).text


def test_a_budget_stops_at_the_shot_that_passes_it():
    e = estimate("seedance_2_5", [f for _, f in SHOTS], 24, 10)  # 4 + 6 = 10 fits, the third does not
    assert e.over_budget and e.stops_at == 3 and "stops before shot 3" in e.text
    assert estimate("seedance_2_5", [f for _, f in SHOTS], 24, 0).stops_at is None  # 0: no limit


def test_a_price_in_the_file_gives_an_amount(monkeypatch):
    gen = load_generator("wan_3_0")
    monkeypatch.setattr("majoor_videotools.core.cost_guard.load_generator", lambda _id: type(gen)(**{**gen.__dict__, "price_per_second": 0.5, "price_unit": "credits"}))
    e = estimate("wan_3_0", [72, 72], 24, 0)
    assert e.seconds == 6.0 and e.price is None and e.amount_text == "3 credits" and "about 3 credits" in e.text  # two 3 s shots at 0.5 a second (no badge outside ComfyUI)


def test_deploy_reports_the_cost_and_asks_only_when_over_the_budget():
    notes, questions = deploy_notes(_workflow("seedance_2_5", 120), SHOTS, 24)
    assert len(notes) == 1 and questions == []
    notes, questions = deploy_notes(_workflow("seedance_2_5", 10), SHOTS, 24)
    assert len(questions) == 1 and questions[0].endswith("Deploy anyway?")
    assert deploy_notes(_workflow("minimax_h3", 10), SHOTS, 24) == ([], [])  # local: free
    assert deploy_notes({"nodes": []}, SHOTS, 24) == ([], []) and deploy_notes(_workflow("seedance_2_5"), [], 24) == ([], [])


def test_the_budget_of_a_saved_workflow_defaults_for_older_files():
    assert selected_generator(_workflow("wan_3_0")) == Choice("wan_3_0", DEFAULT_BUDGET_SECONDS, 0.0)
    assert selected_generator(_workflow("wan_3_0", 30)) == Choice("wan_3_0", 30, 0.0)


def test_the_ledger_counts_a_run_and_refuses_the_take_that_passes_the_budget():
    ledger = Ledger()
    assert ledger.charge("run1", 5, 12) == (5, 0) and ledger.charge("run1", 6, 12) == (11, 0)
    with pytest.raises(ValueError, match="budget reached.*11 s.*6 s more"):
        ledger.charge("run1", 6, 12)
    assert ledger.runs["run1"] == (11, 0)  # the refused take is not counted
    assert ledger.charge("run2", 100, 0) == (100, 0)  # no limit; another run starts from zero
    for i in range(40):
        ledger.charge(f"r{i}", 1, 0)
    assert len(ledger.runs) <= Ledger.KEEP


@pytest.mark.parametrize("name", ("SECATOR Creative Text", "SECATOR Creative Music"))
def test_the_creative_recipes_carry_the_budget(name):
    wf = dp.load_recipe(name)
    assert selected_generator(wf) == Choice("minimax_h3", DEFAULT_BUDGET_SECONDS, 0.0)
    select = next(n for n in wf["nodes"] if n["type"] == "MajoorGeneratorSelect")
    assert [i["name"] for i in select["inputs"]] == ["generator", "max_api_seconds", "max_api_usd"]
    guide = next(n for n in wf["nodes"] if n["type"] == "MarkdownNote" and n.get("title") == "GUIDE")
    assert "MAX API SECONDS" in guide["widgets_values"][0]
