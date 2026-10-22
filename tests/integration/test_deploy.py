import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from majoor_videotools.core import deploy as dp
from majoor_videotools.core.errors import MajoorError

RECIPE_NAME = "minimax_h3_ref2va"
CUTCUT = Path(r"F:\__WORKFLOWS\docs\Cutcut.json")


@pytest.fixture(scope="module")
def recipe():
    return dp.load_recipe(RECIPE_NAME)


def _is_shot_list_get(node):
    return str(node["widgets_values"][0]) == "SHOT_LIST" and any(o.get("type") == "MAJOOR_SHOT_LIST" for o in node.get("outputs", []))


def ids(n):
    return [f"SHOT_{i:03d}" for i in range(1, n + 1)]


def by_type(wf, kind):
    return [n for n in wf["nodes"] if n["type"] == kind]


def feeder(wf, node, name="shot_list"):
    slot = next(s for s in node["inputs"] if s["name"] == name)
    if slot["link"] is None:
        return None
    link = next(l for l in wf["links"] if l[0] == slot["link"])
    return next(n for n in wf["nodes"] if n["id"] == link[1])


def stamp(n):
    return (n.get("properties") or {}).get("majoor_deploy") or {}


def bare(recipe):
    """The recipe's graph without its shot block and finale: what a user has before pressing Create."""
    wf = copy.deepcopy(recipe)
    block = dp.template_block(wf)
    dp.remove_nodes(wf, block.node_ids)
    gone = {g.get("id") for g in block.groups}
    wf["groups"] = [g for g in wf["groups"] if g.get("id") not in gone]
    dp._prune_defs(wf)
    return wf


def test_recipe_is_a_valid_workflow_with_one_block(recipe):
    assert dp.check_workflow(recipe) == []
    block = dp.template_block(recipe)
    assert block.shot_id == "SHOT_001" and block.warnings == []
    kinds = Counter(n["type"] for n in block.nodes)
    assert kinds[dp.SELECT] == 1 and kinds[dp.APPLY] == 1 and kinds["MajoorCompareVideo"] == 1 and kinds[dp.SET] == 3
    assert len(block.defs) == 4 and [n["type"] for n in block.shared_nodes.values()] == ["PrimitiveStringMultiline"]


def test_deploy_builds_a_chained_block_per_shot(recipe):
    wf, report = dp.deploy(recipe, bare(recipe), ids(5))
    assert report.created == ids(5) and report.replaced == [] and report.warnings == []
    assert dp.check_workflow(wf) == []
    selects = sorted(by_type(wf, dp.SELECT), key=lambda n: n["widgets_values_named"]["index"])
    assert [(n["widgets_values_named"]["shot_id"], n["widgets_values_named"]["index"]) for n in selects] == [(s, i + 1) for i, s in enumerate(ids(5))]
    assert [n["widgets_values"][0] for n in selects] == ids(5)

    applies = sorted(by_type(wf, dp.APPLY), key=lambda n: stamp(n)["shot"])
    assert [stamp(n)["shot"] for n in applies] == ids(5)
    source = next(n for n in wf["nodes"] if n["type"] == "MajoorSceneDetectSplit")
    assert feeder(wf, applies[0])["id"] == source["id"]  # the first one starts from the shot list, read straight from the node that makes it
    assert all(feeder(wf, n)["id"] == source["id"] for n in selects) and not [n for n in wf["nodes"] if n["type"] == dp.GET and _is_shot_list_get(n) and stamp(n)]  # no Get SHOT_LIST copy in the new blocks
    for before, after in zip(applies, applies[1:]):
        assert feeder(wf, after)["id"] == before["id"]
    assemble = by_type(wf, dp.ASSEMBLE)[0]
    assert feeder(wf, assemble)["id"] == applies[-1]["id"]
    assert [n for n in by_type(wf, dp.SAVE)] and feeder(wf, by_type(wf, dp.SAVE)[0], "video")["id"] == assemble["id"]
    assert len(wf["definitions"]["subgraphs"]) == 1 + 4 * 5  # the model loader and four definitions per shot
    assert {g["title"] for g in wf["groups"]} >= set(ids(5))
    assert len({n["id"] for n in wf["nodes"]}) == len(wf["nodes"])


def test_every_name_follows_its_shot(recipe):
    wf, _ = dp.deploy(recipe, bare(recipe), ids(3))
    names = Counter(str(n["widgets_values"][0]) for n in wf["nodes"] if n["type"] == dp.SET)
    for shot in ids(3):
        for suffix in ("", "_META", "_GENERATED"):
            assert names[shot + suffix] == 1, (shot, suffix)
    texts = {}
    for n in wf["nodes"]:
        s = stamp(n)
        if s.get("shot") in ids(3):
            plain = copy.deepcopy(n)
            plain["properties"].pop("majoor_deploy")  # the stamp names the recipe's own shot on purpose
            texts.setdefault(s["shot"], []).append(json.dumps(plain))
    for definition in wf["definitions"]["subgraphs"]:
        shots = [s for s in ids(3) if s in definition["name"]]
        if shots:
            texts.setdefault(shots[0], []).append(json.dumps(definition))
    for shot, parts in texts.items():
        others = [s for s in ids(3) if s != shot]
        assert not any(o in p for p in parts for o in others), shot  # nothing of another shot leaked in
    for shot in ids(3)[1:]:
        assert all("SHOT_001" not in p for p in texts[shot])


def test_the_edit_request_is_shared_by_every_shot(recipe):
    wf, _ = dp.deploy(recipe, bare(recipe), ids(4))
    primitives = by_type(wf, "PrimitiveStringMultiline")
    assert len(primitives) == 1
    generators = [n for n in wf["nodes"] if stamp(n).get("shot") in ids(4) and n["type"] in {d["id"] for d in wf["definitions"]["subgraphs"]}
                  and any(s["name"] == "string_b" for s in n["inputs"])]
    assert len(generators) == 4 and all(feeder(wf, g, "string_b")["id"] == primitives[0]["id"] for g in generators)


def test_deploying_again_replaces_the_previous_deployment_and_keeps_shared_edits(recipe):
    start = bare(recipe)
    anchor = {"id": 9000, "type": dp.DEPLOYER, "pos": [0, 0], "size": [300, 200], "inputs": [], "outputs": [], "properties": {}}
    start["nodes"].append(anchor)
    first, _ = dp.deploy(recipe, start, ids(3), anchor_id=9000)
    primitive = by_type(first, "PrimitiveStringMultiline")[0]
    primitive["widgets_values"][0] = "my own edit request"
    again, report = dp.deploy(recipe, first, ids(5), anchor_id=9000)
    assert dp.check_workflow(again) == [] and report.created == ids(5)
    assert len(by_type(again, dp.SELECT)) == 5 and len(by_type(again, dp.APPLY)) == 5 and len(by_type(again, dp.ASSEMBLE)) == 1
    assert len(again["definitions"]["subgraphs"]) == 1 + 4 * 5
    assert [n["widgets_values"][0] for n in by_type(again, "PrimitiveStringMultiline")] == ["my own edit request"]
    shorter, _ = dp.deploy(recipe, again, ids(2), anchor_id=9000)
    assert len(by_type(shorter, dp.SELECT)) == 2 and len(shorter["definitions"]["subgraphs"]) == 1 + 4 * 2
    assert next(n for n in shorter["nodes"] if n["id"] == 9000)["properties"]["majoor_deploy"]["shots"] == ids(2)
    assert len(by_type(shorter, dp.SAVE)) == 1  # the finale is not duplicated


def test_blocks_made_by_hand_are_replaced_only_when_allowed(recipe):
    hand = copy.deepcopy(recipe)  # already holds a SHOT_001 block
    with pytest.raises(MajoorError, match="already has a block for SHOT_001"):
        dp.deploy(recipe, hand, ids(2), replace_existing=False)
    wf, report = dp.deploy(recipe, hand, ids(2))
    assert report.replaced == ["SHOT_001"] and len(by_type(wf, dp.SELECT)) == 2 and dp.check_workflow(wf) == []
    assert len(by_type(wf, dp.ASSEMBLE)) == 1 and feeder(wf, by_type(wf, dp.ASSEMBLE)[0])["id"] in {n["id"] for n in by_type(wf, dp.APPLY)}


def test_finale_is_added_only_when_missing_and_asked(recipe):
    start = bare(recipe)
    dp.remove_nodes(start, {n["id"] for n in start["nodes"] if n["type"] in (dp.ASSEMBLE, dp.SAVE)})
    wf, report = dp.deploy(recipe, start, ids(2), include_finale=False)
    assert not by_type(wf, dp.ASSEMBLE) and any("No Shot Assemble" in w for w in report.warnings)
    wf, report = dp.deploy(recipe, start, ids(2))
    assemble = by_type(wf, dp.ASSEMBLE)
    assert len(assemble) == 1 and len(by_type(wf, dp.SAVE)) == 1 and not report.warnings
    assert feeder(wf, assemble[0])["type"] == dp.APPLY and dp.check_workflow(wf) == []


def test_missing_set_nodes_are_reported(recipe):
    start = bare(recipe)
    dp.remove_nodes(start, {n["id"] for n in start["nodes"] if n["type"] == dp.SET and n["widgets_values"][0] in ("REF", "OLLAMA")})
    _, report = dp.deploy(recipe, start, ids(1))
    assert any("No Set node for: OLLAMA, REF" in w for w in report.warnings)


def test_layout_in_columns_and_input_checks(recipe):
    wf, _ = dp.deploy(recipe, bare(recipe), ids(4), columns=2)
    spots = {(round(g["bounding"][0]), round(g["bounding"][1])) for g in wf["groups"] if g["title"] in ids(4)}
    assert len({x for x, _ in spots}) == 2 and len({y for _, y in spots}) == 2
    for args, message in (([], "No shot to deploy"), (["A", "A"], "unique"), (["bad id"], "unique")):
        with pytest.raises(MajoorError, match=message):
            dp.deploy(recipe, bare(recipe), args)
    with pytest.raises(MajoorError, match="Unknown recipe"):
        dp.load_recipe("nope")
    with pytest.raises(MajoorError, match="Invalid recipe"):
        dp.load_recipe("../secret")
    assert RECIPE_NAME in dp.list_recipes()


def test_input_graph_is_not_modified(recipe):
    start = bare(recipe)
    snapshot = json.dumps(start, sort_keys=True)
    dp.deploy(recipe, start, ids(3))
    assert json.dumps(start, sort_keys=True) == snapshot


def test_shot_ids_that_are_not_numbered_work(recipe):
    wf, _ = dp.deploy(recipe, bare(recipe), ["OPEN", "MIDDLE", "SHOT_010"])
    assert {n["widgets_values"][0] for n in by_type(wf, dp.SET)} >= {"OPEN_META", "MIDDLE_GENERATED", "SHOT_010", "REF", "SHOT_LIST"}
    assert dp.check_workflow(wf) == []


@pytest.mark.skipif(not CUTCUT.exists(), reason="reference workflow not available")
def test_rebuilding_the_hand_made_workflow_gives_the_same_structure(recipe):
    hand = json.loads(CUTCUT.read_text(encoding="utf-8"))
    rebuilt, report = dp.deploy(recipe, copy.deepcopy(hand), ids(7))
    assert dp.check_workflow(rebuilt) == [] and len(report.replaced) == 7
    for kind in (dp.SELECT, dp.APPLY, "MajoorCompareVideo", dp.ASSEMBLE, dp.SAVE, dp.SET):
        assert len(by_type(rebuilt, kind)) == len(by_type(hand, kind)), kind
    assert len(rebuilt["definitions"]["subgraphs"]) == len(hand["definitions"]["subgraphs"])


PLAN_RECIPE = "minimax_h3_ref2va_plan"


@pytest.fixture(scope="module")
def plan_recipe():
    return dp.load_recipe(PLAN_RECIPE)


def test_recipe_is_picked_by_the_kind_of_shots():
    assert dp.pick_recipe("auto", True) == "Minimax H3 TimelineShot Creator" and dp.pick_recipe("auto", False) == RECIPE_NAME
    assert dp.pick_recipe("minimax_h3_ref2va", True) == "minimax_h3_ref2va"  # an explicit choice is kept


def test_plan_recipe_block_is_driven_by_the_plan(plan_recipe):
    assert dp.check_workflow(plan_recipe) == []
    block = dp.template_block(plan_recipe)
    kinds = Counter(n["type"] for n in block.nodes)
    assert block.warnings == [] and not block.shared_nodes
    assert kinds[dp.SELECT] == 1 and kinds[dp.APPLY] == 1 and kinds["MajoorPreviewVideo"] == 1 and kinds["MajoorCompareVideo"] == 0
    names = {str(n["widgets_values"][0]) for n in block.nodes if n["type"] in (dp.SET, dp.GET)}
    assert {"SHOT_001", "SHOT_001_META", "SHOT_001_GENERATED", "SHOT_001_GENSEC"} <= names
    select = next(n for n in block.nodes if n["type"] == dp.SELECT)
    assert [o["name"] for o in select["outputs"]][-4:] == ["generation_seconds", "fx_json", "rhythm_text", "notes"] and select["widgets_values_named"]["frame_sampling"] == "first"
    generate = next(d for d in block.defs.values() if d["name"] == "SHOT_001_GENERATE")
    analysis = next(n for n in generate["nodes"] if n["id"] == 151)
    assert analysis["mode"] == 4  # the LLM analysis of a flat card is bypassed: the prompt of the plan goes through
    h3 = next(d for d in block.defs.values() if d["name"] == "New Subgraph")
    assert next(n for n in h3["nodes"] if n["type"] == "MiniMaxH3FunControlNetApply")["mode"] == 4  # no pose control from a card
    assert all(slot["link"] is None for n in generate["nodes"] if n["id"] == 56 for slot in n["inputs"] if slot["name"] == "ref_videos.ref_video_0")


def test_plan_recipe_deploys_a_block_per_shot_with_its_own_seed(plan_recipe):
    start = copy.deepcopy(plan_recipe)
    dp.remove_nodes(start, dp.template_block(start).node_ids)
    dp._prune_defs(start)
    wf, report = dp.deploy(plan_recipe, start, ids(3))
    assert report.warnings == [] and dp.check_workflow(wf) == []
    sets = Counter(str(n["widgets_values"][0]) for n in wf["nodes"] if n["type"] == dp.SET)
    assert all(sets[f"{s}_GENSEC"] == 1 for s in ids(3))
    selects = sorted(by_type(wf, dp.SELECT), key=lambda n: n["widgets_values_named"]["index"])
    for select, shot in zip(selects, ids(3)):
        link = next(l for l in wf["links"] if l[1] == select["id"] and l[2] == 6)  # generation_seconds
        assert next(n for n in wf["nodes"] if n["id"] == link[3])["widgets_values"][0] == f"{shot}_GENSEC"
    generators = sorted((n for n in wf["nodes"] if stamp(n).get("shot") in ids(3) and "noise_seed" in (n.get("widgets_values_named") or {})), key=lambda n: stamp(n)["shot"])
    seeds = [n["widgets_values_named"]["noise_seed"] for n in generators]
    assert len(seeds) == 3 and seeds[1] == seeds[0] + 1 and seeds[2] == seeds[0] + 2
    for shot in ids(3):
        generate = next(d for d in wf["definitions"]["subgraphs"] if d["name"] == f"{shot}_GENERATE")
        assert {str(n["widgets_values"][0]) for n in generate["nodes"] if n["type"] == dp.GET} >= {f"{shot}_GENSEC", shot}
        assert next(n for n in generate["nodes"] if n["id"] == 151)["mode"] == 4
        save = next(n for n in generate["nodes"] if n["type"] == "SaveVideo")
        assert save["widgets_values"][0] == f"MajoorVideoTools/Auto/{shot}"


TIMELINESHOT = "Minimax H3 TimelineShot Creator"
WORKING = Path(r"F:\__WORKFLOWS\docs\AutoEdit_Workflow_v001.json")


def _bare_of(recipe_wf):
    wf = copy.deepcopy(recipe_wf)
    block = dp.template_block(wf)
    dp.remove_nodes(wf, block.node_ids)
    gone = {g.get("id") for g in block.groups}
    wf["groups"] = [g for g in wf["groups"] if g.get("id") not in gone]
    dp._prune_defs(wf)
    return wf


def test_auto_takes_the_timelineshot_recipe_for_plan_shots_and_the_video_one_otherwise():
    assert dp.pick_recipe("auto", True) == TIMELINESHOT and dp.pick_recipe("auto", False) == "minimax_h3_ref2va"
    assert dp.recipe_info(TIMELINESHOT)["kind"] == "plan" and TIMELINESHOT in dp.list_recipes()
    assert dp.pick_recipe(TIMELINESHOT, False) == TIMELINESHOT  # an explicit choice is kept


def test_timelineshot_blocks_read_the_shot_list_straight_from_create_timeline():
    recipe = dp.load_recipe(TIMELINESHOT)
    assert dp.check_workflow(recipe) == []
    block = dp.template_block(recipe)
    assert block.warnings == [] and not block.shared_nodes and len(block.list_inputs) == 2 and [g["title"] for g in block.groups] == ["SHOT_001", "SHOT_001_GENERATE"]
    kinds = Counter(n["type"] for n in block.nodes)
    assert kinds["StringConcatenate"] == 2 and kinds[dp.SELECT] == 1 and kinds[dp.APPLY] == 1 and kinds[dp.GET] == 2  # the brief of the shot, no Get of the shot list
    anchor = next(n for n in recipe["nodes"] if n["type"] == dp.DEPLOYER)
    timeline = next(n for n in recipe["nodes"] if n["type"] == "MajoorCreateTimeline")
    wf, report = dp.deploy(recipe, _bare_of(recipe), ids(4), anchor_id=anchor["id"], columns=2)
    assert report.warnings == [] and dp.check_workflow(wf) == [] and report.created == ids(4)
    selects = sorted(by_type(wf, dp.SELECT), key=lambda n: n["widgets_values_named"]["index"])
    assert [n["widgets_values"][0] for n in selects] == ids(4)
    assert all(feeder(wf, n)["id"] == timeline["id"] for n in selects)  # wired directly, not through a Reroute or a Get node
    applies = sorted(by_type(wf, dp.APPLY), key=lambda n: stamp(n)["shot"])
    assert feeder(wf, applies[0])["id"] == timeline["id"] and all(feeder(wf, b)["id"] == a["id"] for a, b in zip(applies, applies[1:]))
    assert feeder(wf, by_type(wf, dp.ASSEMBLE)[0])["id"] == applies[-1]["id"]
    assert not [n for n in wf["nodes"] if stamp(n) and n["type"] in (dp.GET,) and str(n["widgets_values"][0]) == "SHOT_LIST"]
    titles = sorted(g["title"] for g in wf["groups"] if g["title"].startswith("SHOT_"))
    assert titles == sorted([*ids(4), *(f"{s}_GENERATE" for s in ids(4))])  # both groups of every block
    assert len(by_type(wf, "StringConcatenate")) == 8 and len(wf["definitions"]["subgraphs"]) == len(_bare_of(recipe)["definitions"]["subgraphs"]) + 4 * 4
    again, _ = dp.deploy(recipe, wf, ids(2), anchor_id=anchor["id"])
    assert len(by_type(again, dp.SELECT)) == 2 and dp.check_workflow(again) == []


def test_a_shot_list_wire_through_a_reroute_or_a_get_still_ends_at_the_source():
    recipe = dp.load_recipe(TIMELINESHOT)
    timeline = next(n for n in recipe["nodes"] if n["type"] == "MajoorCreateTimeline")
    start = _bare_of(recipe)
    anchor = next(n for n in start["nodes"] if n["type"] == dp.DEPLOYER)
    # the deployer is fed through a Reroute: the source is found all the same
    reroute = {"id": 9001, "type": "Reroute", "pos": [0, 0], "size": [75, 26], "flags": {}, "mode": 0, "inputs": [{"name": "", "type": "*", "link": None}], "outputs": [{"name": "", "type": "MAJOOR_SHOT_LIST", "links": None}], "properties": {}}
    start["nodes"].append(reroute)
    dp._drop_links(start, {anchor["inputs"][0]["link"]})
    alloc = dp.Alloc(start)
    dp._connect(start, alloc, next(n for n in start["nodes"] if n["id"] == timeline["id"]), 0, reroute, 0, "MAJOOR_SHOT_LIST")
    dp._connect(start, alloc, reroute, 0, anchor, 0, "MAJOOR_SHOT_LIST")
    source = dp.shot_list_source(start, anchor)
    assert source is not None and source[0]["id"] == timeline["id"] and source[1] == 0
    wf, report = dp.deploy(recipe, start, ids(2), anchor_id=anchor["id"])
    assert report.warnings == [] and all(feeder(wf, n)["id"] == timeline["id"] for n in by_type(wf, dp.SELECT))
    lonely = copy.deepcopy(start)  # nothing to read the shot list from: a clear warning, not a broken graph
    dp.remove_nodes(lonely, {timeline["id"], 9001})
    _, report = dp.deploy(recipe, lonely, ids(2))
    assert any("No Create Timeline or Scene Detect" in w for w in report.warnings)


def test_a_switch_between_two_sources_gives_the_one_it_selects():
    def node(nid, kind, inputs=(), outputs=(), values=None):
        return {"id": nid, "type": kind, "inputs": [{"name": n, "link": l} for n, l in inputs], "outputs": [{"name": n, "links": []} for n in outputs], "widgets_values": values or []}

    def graph(chosen):
        wf = {"nodes": [node(1, "MajoorCreateTimeline", outputs=["shot_list"]), node(2, "MajoorSceneDetectSplit", outputs=["shot_list"]),
                        node(3, dp.SWITCH, inputs=[("switch", None), ("on_false", 10), ("on_true", 11)], outputs=["output"], values=[chosen]),
                        node(4, dp.DEPLOYER, inputs=[("shot_list", 12)])],
              "links": [[10, 1, 0, 3, 1, "MAJOOR_SHOT_LIST"], [11, 2, 0, 3, 2, "MAJOOR_SHOT_LIST"], [12, 3, 0, 4, 0, "MAJOOR_SHOT_LIST"]]}
        return wf, wf["nodes"][3]

    for chosen, expected in ((False, 1), (True, 2)):
        wf, anchor = graph(chosen)
        assert dp.shot_list_source(wf, anchor)[0]["id"] == expected


def test_the_edit_request_of_the_remix_can_be_answered_by_an_llm_node_of_the_graph(recipe):
    title = next(n["title"] for n in dp.template_block(recipe).shared_nodes.values())
    assert title == "REMIX · EDIT REQUEST (what to replace)"
    start = _bare_of(recipe)
    dp.remove_nodes(start, set(dp.template_block(recipe).shared_nodes))  # the graph has an LLM node under that title instead of the recipe's primitive
    ollama = {"id": 9100, "type": "OllamaChat", "title": title, "pos": [0, 0], "size": [300, 200], "flags": {}, "mode": 0, "inputs": [], "properties": {},
              "outputs": [{"name": "result", "type": "STRING", "links": None}, {"name": "thinking", "type": "STRING", "links": None}]}
    start["nodes"].append(ollama)
    wf, report = dp.deploy(recipe, start, ids(2))
    requests = [n for n in wf["nodes"] if n.get("title") == title]
    assert [n["id"] for n in requests] == [9100], "the LLM node is used, no primitive is added next to it"
    feeds = {l[3] for l in wf["links"] if l[1] == 9100}
    assert len(feeds) == 2 and report.warnings == []


@pytest.mark.skipif(not WORKING.exists(), reason="working workflow not available")
def test_the_working_workflow_is_read_even_though_its_select_shot_was_left_on_another_shot():
    raw = json.loads(WORKING.read_text(encoding="utf-8"))
    assert next(n for n in raw["nodes"] if n["type"] == dp.SELECT)["widgets_values"][0] != "SHOT_001"  # the Select Shot says one shot, the Set/Get nodes another
    block = dp.template_block(raw)
    assert block.shot_id == "SHOT_001" and len(block.list_inputs) == 2 and [g["title"] for g in block.groups] == ["SHOT_001", "SHOT_001_GENERATE"]
    assert not block.shared_nodes  # the Reroute in front of the Select Shot is a wire, not a node to copy
    recipe = dp.load_recipe(TIMELINESHOT)
    wf, report = dp.deploy(recipe, copy.deepcopy(raw), ids(3))
    assert dp.check_workflow(wf) == [] and report.replaced == ["SHOT_001"]
    names = Counter(str(n["widgets_values"][0]) for n in wf["nodes"] if n["type"] == dp.SET and str(n["widgets_values"][0]).startswith("SHOT_00"))
    assert all(count == 1 for count in names.values()), names  # nothing of the hand-made block is left behind


def test_the_first_picture_follows_the_set_node_of_the_graph_whether_it_is_named_ref_or_ref1():
    recipe = dp.load_recipe("Text Audio & Refs Mode Minimax H3 ")  # its blocks read REF1
    start = bare(recipe)
    for node in start["nodes"]:
        if node["type"] == dp.SET and node["widgets_values"][0] == "REF1":
            node["widgets_values"][0], node["title"] = "REF", "Set_REF"
    out, report = dp.deploy(recipe, start, ids(2))
    assert any("read as REF" in w for w in report.warnings) and not any("REF1" in w and "No Set node" in w for w in report.warnings)
    gets = [n["widgets_values"][0] for n in [*out["nodes"], *(n for d in out["definitions"]["subgraphs"] for n in d["nodes"])] if n["type"] == dp.GET]
    assert "REF1" not in gets and "REF" in gets
    start = bare(recipe)
    dp.remove_nodes(start, {n["id"] for n in start["nodes"] if n["type"] == dp.SET and n["widgets_values"][0] == "REF1"})
    _, report = dp.deploy(recipe, start, ids(1))
    assert any("Without REF or REF1 the first reference picture reaches neither H3 nor the LLM" in w for w in report.warnings)
