import copy
from collections import Counter

import pytest

from majoor_videotools.core import deploy as dp

CREATIVE = ("SECATOR Creative Text", "SECATOR Creative Music")
IMAGES = [f"image_{i}" for i in range(1, 10)]


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


@pytest.mark.parametrize("name", CREATIVE)
def test_the_recipe_offers_the_video_model_choice(name):
    wf = dp.load_recipe(name)
    kinds = Counter(n["type"] for n in wf["nodes"])
    assert kinds["MajoorGeneratorSelect"] == 1 and kinds["MajoorGenerateShot"] == 2 and kinds["MajoorGeneratorIs"] == 1
    assert dp.check_workflow(wf) == []
    timeline = next(n for n in wf["nodes"] if n["type"] == "MajoorCreateTimeline")
    assert _source_of(wf, timeline, "generator")["widgets_values"] == ["GENERATOR"]  # the plan follows the model
    for take in (n for n in wf["nodes"] if n["type"] == "CreateVideo"):
        for slot in ("images", "audio", "fps"):
            assert _source_of(wf, take, slot)["type"] == "ComfySwitchNode"  # the take is the H3 one or the API one, chosen lazily


@pytest.mark.parametrize("name", CREATIVE)
def test_every_shot_block_has_its_own_api_branch(name):
    recipe = dp.load_recipe(name)
    wf, report = dp.deploy(recipe, _bare(recipe), [f"SHOT_{i:03d}" for i in range(1, 4)])
    assert dp.check_workflow(wf) == []
    generated = [n for n in wf["nodes"] if n["type"] == "MajoorGenerateShot"]
    assert len(generated) == 6  # a take and a retry per shot
    for node in generated:
        assert _source_of(wf, node, "generator")["widgets_values"] == ["GENERATOR"]
        assert _source_of(wf, node, "seconds")["type"] == dp.SELECT
        assert _source_of(wf, node, "prompt") is not None and _source_of(wf, node, "image_1") is not None
    assert len({n["widgets_values_named"]["seed"] for n in generated}) >= 3  # the retry does not repeat the seed of the take
