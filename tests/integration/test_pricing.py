import json
from pathlib import Path

import pytest

pytest.importorskip("jsonata")  # the evaluator of the price badges (requirements.txt)

from majoor_videotools.core import cost_guard
from majoor_videotools.core.cost_guard import Ledger, Settings, deploy_notes, estimate, settings_of, shot_price
from majoor_videotools.core.pricing import Price, ZERO, evaluate

# the price badges of the partner nodes as the frontend receives them (object_info), taken from ComfyUI 0.44.2
BADGES = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "price_badges.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def comfy_badges(monkeypatch):
    monkeypatch.setattr(cost_guard, "badge_of", lambda class_type: BADGES.get(class_type))


def test_seedance_price_follows_the_badge():
    price = shot_price("seedance_2_5", 6, Settings("9:16", "720p", True, images=1))
    assert price.low == price.high and price.high == pytest.approx(1.9967805)  # 6 s at 720p, no reference video
    with_video = shot_price("seedance_2_5", 6, Settings("9:16", "720p", True, images=1, videos=1))
    assert with_video.low == pytest.approx(1.194336) and with_video.high == pytest.approx(7.124832)  # a reference video makes the price a range
    assert shot_price("seedance_2_5", 6, Settings("9:16", "1080p")).high > price.high  # a higher resolution costs more


def test_wan_badge_is_read_although_the_widget_is_spelled_in_capitals():
    price = shot_price("wan_3_0", 5, Settings("9:16", "720p"))  # the node says 720P, the table of the badge says 720p
    assert price.low == pytest.approx(0.715) and price.high == pytest.approx(2.86)


def test_ltx_prices_follow_the_size_and_the_model():
    pro = shot_price("ltx_2_5_pro", 5, Settings("9:16", "720p", images=1))
    fast = shot_price("ltx_2_5_fast", 5, Settings("9:16", "1080p", images=1))
    assert pro.high == pytest.approx(0.1716 * 5) and fast.high == pytest.approx(0.1859 * 5)
    assert shot_price("ltx_2_5_pro", 5, Settings("9:16", "720p", images=0)).high == pytest.approx(0.858)  # the text-to-video node has the same table


def test_a_price_is_none_when_nothing_can_be_known():
    assert shot_price("minimax_h3", 5) is None  # a local model
    assert shot_price("ltx_2_5_pro", 5, Settings("1:1", "720p")) is None  # a format the model does not make
    assert evaluate(None, {}, []) is None and evaluate({"engine": "jsonata", "expr": "(((", "depends_on": {}}, {}, []) is None


def test_the_estimate_adds_up_the_badges_of_the_takes():
    shots = [72, 130, 48]  # 3 s, 5.4 s, 2 s at 24 fps: Seedance asks for 4 + 6 + 4 s
    e = estimate("seedance_2_5", shots, 24, 120, 0.0, Settings("9:16", "720p", images=1))
    each = [shot_price("seedance_2_5", s, Settings("9:16", "720p", images=1)) for s in (4, 6, 4)]
    assert e.price.high == pytest.approx(sum(p.high for p in each)) and e.price == sum(each, ZERO)
    assert f"about ${e.price.high:.2f}" in e.text and "install jsonata-python" not in e.text


def test_a_dollar_budget_stops_the_run_where_the_badges_pass_it():
    shots = [72, 130, 48]
    cheap, dear = shot_price("seedance_2_5", 4, Settings(images=1)).high, shot_price("seedance_2_5", 6, Settings(images=1)).high
    e = estimate("seedance_2_5", shots, 24, 0, cheap + dear + 0.01, Settings(images=1))  # the third take would pass it
    assert e.over_budget and e.stops_at == 3 and "stops before shot 3" in e.text and "$" in e.text
    assert estimate("seedance_2_5", shots, 24, 0, 1000, Settings(images=1)).stops_at is None


def test_deploy_reports_dollars_from_the_widgets_and_wires_of_the_workflow():
    workflow = {"nodes": [
        {"type": "MajoorGeneratorSelect", "widgets_values": ["seedance_2_5", 0, 2.0], "widgets_values_named": {"generator": "seedance_2_5", "max_api_seconds": 0, "max_api_usd": 2.0}},
        {"type": "MajoorGenerateShot", "widgets_values_named": {"aspect_ratio": "9:16", "resolution": "720p", "generate_audio": True},
         "inputs": [{"name": "image_1", "link": 4}, {"name": "image_2", "link": 5}, {"name": "image_3", "link": None}, {"name": "reference_frames", "link": 6}]},
    ]}
    assert settings_of(workflow) == Settings("9:16", "720p", True, images=2, videos=1, audios=0)
    notes, questions = deploy_notes(workflow, [("SHOT_001", 144), ("SHOT_002", 144)], 24)
    assert "$" in notes[0] and len(questions) == 1 and "Over the budget of $2" in questions[0]  # a reference video makes a take cost up to a few dollars


def test_the_ledger_counts_dollars_too():
    ledger = Ledger()
    assert ledger.charge("r", 5, 0, 1.5, 4.0) == (5, 1.5) and ledger.charge("r", 5, 0, 2.0, 4.0) == (10, 3.5)
    with pytest.raises(ValueError, match="about \\$3.50 already.*\\$1.00 more would pass the \\$4"):
        ledger.charge("r", 5, 0, 1.0, 4.0)
    assert ledger.runs["r"] == (10, 3.5)


def test_prices_add_and_read():
    assert (Price(1, 2) + Price(0.5, 1)).text == "$1.50 to $3.00" and Price(1.9968, 1.9968).text == "$2.00"
