import json
import re

import pytest

from majoor_videotools.core import deploy as dp
from majoor_videotools.core.skills import list_skills

from conftest import ROOT

NAMES = ("SECATOR Remix", "SECATOR Creative Text", "SECATOR Creative Music")


def _load(name):
    return json.loads((ROOT / "workflows" / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", NAMES)
def test_the_workflow_is_also_its_recipe(name):
    assert (ROOT / "workflows" / f"{name}.json").read_bytes() == (ROOT / "recipes" / f"{name}.json").read_bytes()
    deploy = next(n for n in _load(name)["nodes"] if n["type"] == dp.DEPLOYER)
    assert deploy["widgets_values"][0] == name and name in dp.list_recipes()


@pytest.mark.parametrize("name", NAMES)
def test_the_block_of_a_workflow_is_deployed_for_every_shot(name):
    wf = _load(name)
    assert dp.template_block(wf).shot_id == "SHOT_001" and not dp.check_workflow(wf)
    out, report = dp.deploy(wf, wf, ["SHOT_001", "SHOT_002", "SHOT_003"])
    assert not report.warnings and not dp.check_workflow(out)
    assert sorted(n["widgets_values"][0] for n in out["nodes"] if n["type"] == dp.SELECT) == ["SHOT_001", "SHOT_002", "SHOT_003"]
    assert sum(n["type"] == dp.APPLY for n in out["nodes"]) == 3


@pytest.mark.parametrize("name", NAMES)
def test_the_skills_of_a_workflow_exist(name):
    wf = _load(name)
    graphs = [wf["nodes"], *(d["nodes"] for d in wf["definitions"]["subgraphs"])]
    used = {n["widgets_values"][0] for nodes in graphs for n in nodes if n["type"] == "MajoorEditSkills"}
    assert used and used <= set(list_skills())


def test_a_workflow_has_no_mode_tag_and_no_edit_mode():
    for name in NAMES:
        text = (ROOT / "workflows" / f"{name}.json").read_text(encoding="utf-8")
        assert "MajoorEditMode" not in text and "majoor_mode" not in text


@pytest.mark.parametrize("name", NAMES)
def test_the_nodes_do_not_overlap_and_the_notes_list_the_dependencies(name):
    wf = _load(name)

    def clashes(nodes):
        rects = []
        for n in nodes:
            x, y = n["pos"]
            w, h = n["size"]
            if n.get("flags", {}).get("collapsed"):
                w, h = min(w, 260), 30
            rects.append((n["id"], x, y - 30, x + w, y + h))
        return [(a[0], b[0]) for i, a in enumerate(rects) for b in rects[i + 1:] if a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4]]

    assert not clashes(wf["nodes"])
    assert not any(clashes(d["nodes"]) for d in wf["definitions"]["subgraphs"])
    notes = {n["title"].split(" · ")[0]: n["widgets_values"][0] for n in wf["nodes"] if n["type"] == "MarkdownNote"}
    assert {"GUIDE", "DEPENDENCIES", "WIRING"} <= set(notes)
    models = {m for loader in wf["nodes"] if loader["type"] in ("UNETLoader", "CLIPLoader", "VAELoader", "ModelPatchLoader") for m in loader["widgets_values"][:1]}
    assert models and all(m in notes["DEPENDENCIES"] and "huggingface.co/Comfy-Org/" in notes["DEPENDENCIES"] for m in models)
    sets = {n["widgets_values"][0] for n in wf["nodes"] if n["type"] == "SetNode"}
    assert all(f"`{s}`" in notes["WIRING"] for s in sets)


@pytest.mark.parametrize("name", NAMES)
def test_five_pictures_and_the_controls(name):
    wf = _load(name)
    loaders = [n for n in wf["nodes"] if n["type"] == "LoadImage"]
    assert [n["title"].split(" · ")[0] for n in loaders] == [f"REF {k}" for k in range(1, 6)] and [n["mode"] for n in loaders] == [0, 4, 4, 4, 4]
    titles = [n.get("title", "") for n in wf["nodes"]]
    assert any(t.startswith("VOICE ON") for t in titles) and any("TURBO" in t for t in titles)
    batch = next(n for n in wf["nodes"] if n["type"] == "BatchImagesNode")
    assert [i["name"] for i in batch["inputs"]] == [f"images.image{k}" for k in range(5)]
    h3 = next(n for n in wf["nodes"] if n["type"].count("-") == 4 and any(i["name"] == "ref_images.ref_image_4" for i in n["inputs"]))
    assert all(h3["inputs"][[i["name"] for i in h3["inputs"]].index(f"ref_images.ref_image_{k}")]["link"] is not None for k in range(5))


def test_the_creative_workflows_make_places_and_the_remix_the_sound():
    text, music, remix = (_load(n) for n in (NAMES[1], NAMES[2], NAMES[0]))
    for wf in (text, music):
        assert any(d["name"].startswith("Plate") for d in wf["definitions"]["subgraphs"])
        planner = next(n for n in wf["nodes"] if n["type"] == "MajoorEditSkills" and n["widgets_values"][0] == "timeline_planner")
        assert next(i for i in planner["inputs"] if i["name"] == "locations")["link"] is not None
    assert any(d["name"].startswith("Sound") for d in text["definitions"]["subgraphs"]) and not any(d["name"].startswith("Sound") for d in music["definitions"]["subgraphs"])
    assert any(n["type"] == "LoadAudio" and n["mode"] == 0 for n in music["nodes"])
    assemble = next(n for n in remix["nodes"] if n["type"] == "MajoorShotAssemble")
    assert {"replace_source_audio", "voice_shots", "music"} <= {i["name"] for i in assemble["inputs"] if i["link"] is not None}


@pytest.mark.parametrize("name", NAMES)
def test_the_values_of_edit_skills_follow_its_widgets(name):
    """dialogue, locations, width, height, then the two buttons: a shift puts a text where an integer goes and ComfyUI refuses the whole planner."""
    wf = _load(name)
    skills = [n for n in wf["nodes"] if n["type"] == "MajoorEditSkills"] + [n for d in wf["definitions"]["subgraphs"] for n in d["nodes"] if n["type"] == "MajoorEditSkills"]
    assert skills
    for node in skills:
        values = node["widgets_values"]
        assert len(values) == 24 and values[18] in ("", None)
        assert isinstance(values[19], bool) and values[20] == 0 and values[21] == 0 and values[22:] == [None, None]


@pytest.mark.parametrize("name", NAMES)
def test_every_variable_of_a_math_expression_is_wired(name):
    """ComfyUI refuses to run a ComfyMathExpression whose variable has no input ('c' is not defined): the H3 size, the number of frames..."""
    wf = _load(name)
    nodes = list(wf["nodes"]) + [n for d in wf["definitions"]["subgraphs"] for n in d["nodes"]]
    maths = [n for n in nodes if n["type"] == "ComfyMathExpression"]
    assert maths
    for node in maths:
        used = set(re.findall(r"[a-z]", node["widgets_values"][0]))
        wired = {i["name"].split(".")[-1] for i in node["inputs"] if i.get("link") is not None}
        assert used <= wired, f"{node['id']}: {node['widgets_values'][0]} uses {sorted(used - wired)} without a link"


@pytest.mark.parametrize("name", NAMES)
def test_a_widget_of_a_subgraph_ends_in_a_widget(name):
    """The value of a widget given to a sub-graph reaches its target only if that target is a widget: a math variable or a socket drops it ('c' is not defined at run time)."""
    wf = _load(name)
    definitions = {d["id"]: d for d in wf["definitions"]["subgraphs"]}
    checked = 0
    for node in wf["nodes"]:
        definition = definitions.get(node["type"])
        for given in (node.get("inputs", []) if definition else []):
            if not given.get("widget"):
                continue
            source = next(i for i in definition["inputs"] if i["name"] == given["name"])
            targets = {link["target_id"]: link["target_slot"] for link in definition["links"] if link["id"] in source["linkIds"]}
            nodes = {n["id"]: n for n in definition["nodes"]}
            assert targets and all(nodes[t]["inputs"][slot].get("widget") for t, slot in targets.items()), f"{definition['name']}: {given['name']} does not end in a widget"
            checked += 1
    assert checked
