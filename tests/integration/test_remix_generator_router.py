import copy
from collections import Counter

from majoor_videotools.core import deploy as dp
from majoor_videotools.core.cost_guard import Choice, DEFAULT_BUDGET_SECONDS, selected_generator

REMIX = "HyperKut Remix"


def _bare(recipe):
    wf = copy.deepcopy(recipe)
    block = dp.template_block(wf)
    dp.remove_nodes(wf, block.node_ids)
    gone = {g.get("id") for g in block.groups}
    wf["groups"] = [g for g in wf["groups"] if g.get("id") not in gone]
    dp._prune_defs(wf)
    return wf


def _source_of(wf, node, name):
    slot = next(s for s in node["inputs"] if s["name"] == name)
    if slot.get("link") is None:
        return None
    link = next(l for l in wf["links"] if l[0] == slot["link"])
    return next(n for n in wf["nodes"] if n["id"] == link[1])


def test_the_remix_offers_the_video_model_choice_in_edit_mode():
    wf = dp.load_recipe(REMIX)
    kinds = Counter(n["type"] for n in wf["nodes"])
    assert kinds["MajoorGeneratorSelect"] == 1 and kinds["MajoorGenerateShot"] == 2 and kinds["MajoorGeneratorIs"] == 1
    assert dp.check_workflow(wf) == []
    assert selected_generator(wf) == Choice("minimax_h3", DEFAULT_BUDGET_SECONDS, 0.0)
    for take in (n for n in wf["nodes"] if n["type"] == "MajoorGenerateShot"):
        assert take["widgets_values_named"]["task"] == "edit"  # a remix changes the shot of the source
        assert _source_of(wf, take, "source_video")["type"] == dp.SELECT  # the video that is changed is the shot itself
        assert _source_of(wf, take, "image_1") is not None and _source_of(wf, take, "reference_frames") is None
    for video in (n for n in wf["nodes"] if n["type"] == "CreateVideo"):
        for slot in ("images", "audio", "fps"):
            assert _source_of(wf, video, slot)["type"] == "ComfySwitchNode"


def test_the_remix_prompt_writer_follows_the_model():
    wf = dp.load_recipe(REMIX)
    sub, skills = next((d, n) for d in wf["definitions"]["subgraphs"] for n in d["nodes"] if n["type"] == "MajoorEditSkills" and (n.get("widgets_values") or [""])[0] == "remix_shot_prompt")
    link = next(l for l in sub["links"] if l["target_id"] == skills["id"] and skills["inputs"][l["target_slot"]]["name"] == "generator")
    assert sub["inputs"][link["origin_slot"]]["name"] == "generator"
    instance = next(n for n in wf["nodes"] if n["type"] == sub["id"])
    assert _source_of(wf, instance, "generator")["widgets_values"] == ["GENERATOR"]


def test_every_remix_block_has_its_own_edit_branch():
    recipe = dp.load_recipe(REMIX)
    wf, _ = dp.deploy(recipe, _bare(recipe), ["SHOT_001", "SHOT_002", "SHOT_003"])
    assert dp.check_workflow(wf) == []
    takes = [n for n in wf["nodes"] if n["type"] == "MajoorGenerateShot"]
    assert len(takes) == 6
    for take in takes:
        assert _source_of(wf, take, "generator")["widgets_values"] == ["GENERATOR"]
        assert _source_of(wf, take, "source_video")["type"] == dp.SELECT
    assert len({n["widgets_values_named"]["seed"] for n in takes}) >= 3
