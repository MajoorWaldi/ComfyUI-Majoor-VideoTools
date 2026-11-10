"""A recipe that Deploy Shots reads (recipes/) and the workflow a user opens (workflows/) under the same name are one file in two places:
a fix made on one side only would make Deploy run another graph than the one on the screen."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHARED = sorted(p.name for p in (ROOT / "recipes").glob("*.json") if (ROOT / "workflows" / p.name).is_file())


def test_the_creative_recipes_have_a_workflow_copy():
    assert {"SECATOR Creative Text.json", "SECATOR Creative Music.json", "SECATOR Remix.json"} <= set(SHARED)


@pytest.mark.parametrize("name", SHARED)
def test_a_recipe_and_its_workflow_are_the_same_file(name):
    assert (ROOT / "recipes" / name).read_bytes() == (ROOT / "workflows" / name).read_bytes(), f"recipes/{name} and workflows/{name} differ: copy the fixed one over the other"


def test_no_template_names_a_personal_file():
    for folder in ("recipes", "workflows", "HyperKut Studio/workflows"):
        for path in (ROOT / folder).rglob("*.json"):
            assert "ChatGPT Image" not in path.read_text(encoding="utf-8"), path
