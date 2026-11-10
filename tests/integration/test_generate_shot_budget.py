"""The budget of Generate Shot (API) on its real path: the node, the budget of Generator Select, the ledger and the held references.
ComfyUI is not needed: its few names the node imports are stood in for."""
import importlib
import sys
import types

import pytest

from majoor_videotools.core import cost_guard
from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.pricing import Price


class _Out:
    def __init__(self, node, i):
        self.node, self.i = node, i


class _Node:
    def __init__(self, kind, inputs):
        self.kind, self.inputs = kind, inputs

    def out(self, i):
        return _Out(self, i)


class _Graph:
    def __init__(self):
        self.nodes = []

    def node(self, kind, **inputs):
        self.nodes.append(_Node(kind, inputs))
        return self.nodes[-1]

    def finalize(self):
        return {str(i): {"class_type": n.kind} for i, n in enumerate(self.nodes)}


class _NodeOutput:
    def __init__(self, *values, expand=None, ui=None):
        self.values, self.expand, self.ui = values, expand, ui


class _Prompt:
    def __init__(self, nodes):
        self.nodes = nodes

    def all_node_ids(self):
        return list(self.nodes)

    def get_node(self, node_id):
        return self.nodes[node_id]


@pytest.fixture
def gs(monkeypatch, tmp_path):
    io = types.SimpleNamespace(ComfyNode=type("ComfyNode", (), {}), NodeOutput=_NodeOutput, Schema=object)
    latest = types.ModuleType("comfy_api.latest")
    latest.io = io
    graph_utils = types.ModuleType("comfy_execution.graph_utils")
    graph_utils.GraphBuilder = _Graph
    server = types.ModuleType("server")
    server.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(last_prompt_id="p1"))
    for name, module in {"comfy_api": types.ModuleType("comfy_api"), "comfy_api.latest": latest, "comfy_execution": types.ModuleType("comfy_execution"),
                         "comfy_execution.graph_utils": graph_utils, "server": server}.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "majoor_videotools.nodes.generate_shot", raising=False)
    module = importlib.import_module("majoor_videotools.nodes.generate_shot")
    module.LEDGER = cost_guard.Ledger(tmp_path / "ledger.json")
    module.HELD.clear()
    yield module, server.PromptServer.instance
    sys.modules.pop("majoor_videotools.nodes.generate_shot", None)


def _run(module, select: dict, price=None, monkeypatch=None, **kw):
    module.MajoorGenerateShot.hidden = types.SimpleNamespace(dynprompt=_Prompt({"GS": {"class_type": "MajoorGeneratorSelect", "inputs": select}}))
    if monkeypatch is not None:
        monkeypatch.setattr(module, "evaluate", lambda *_a: price)
    args = dict(generator="seedance_2_5", prompt="a shot", seconds=5.0, aspect_ratio="16:9", resolution="720p", generate_audio=True, seed=1, image_1=[["pixels"]])
    return module.MajoorGenerateShot.execute(**{**args, **kw})


def test_a_budget_in_dollars_with_no_price_refuses_the_take(gs, monkeypatch):
    module, _ = gs
    with pytest.raises(MajoorError, match="price of this take cannot be read"):
        _run(module, {"max_api_seconds": 0, "max_api_usd": 5.0}, None, monkeypatch)
    assert module.LEDGER.runs == {}  # nothing counted, nothing called
    _run(module, {"max_api_seconds": 0, "max_api_usd": 0.0}, None, monkeypatch)  # no budget in dollars: the seconds are counted


def test_the_dollars_of_the_takes_add_up_until_the_budget(gs, monkeypatch):
    module, _ = gs
    _run(module, {"max_api_seconds": 0, "max_api_usd": 2.0}, Price(0.8, 0.9), monkeypatch)
    _run(module, {"max_api_seconds": 0, "max_api_usd": 2.0}, Price(0.8, 0.9), monkeypatch)
    with pytest.raises(MajoorError, match="MAX API USD"):
        _run(module, {"max_api_seconds": 0, "max_api_usd": 2.0}, Price(0.8, 0.9), monkeypatch)


def test_a_budget_key_shares_one_budget_across_prompts_and_restarts(gs, monkeypatch, tmp_path):
    module, server = gs
    select = {"max_api_seconds": 12, "max_api_usd": 0.0, "budget_key": "job42"}
    _run(module, select, None, monkeypatch)
    server.last_prompt_id = "p2"  # the next shot is another prompt: without a key it would start from zero
    _run(module, select, None, monkeypatch)
    module.LEDGER = cost_guard.Ledger(tmp_path / "ledger.json")  # ComfyUI restarted: the count is read back from disk
    with pytest.raises(MajoorError, match="10 s of video already"):
        _run(module, select, None, monkeypatch)
    server.last_prompt_id = "p3"
    _run(module, {"max_api_seconds": 12, "max_api_usd": 0.0}, None, monkeypatch)  # no key: the budget of this prompt only


def test_the_held_references_are_taken_once_and_dropped_with_their_prompt(gs, monkeypatch):
    module, server = gs
    out = _run(module, {"max_api_seconds": 0}, None, monkeypatch)
    tokens = list(module.HELD["p1"])
    assert len(tokens) == 1  # the one picture
    picture = module.MajoorHeldImage.execute(tokens[0]).values[0]
    assert picture is not None and module.HELD["p1"] == {}  # read once, then out of memory
    with pytest.raises(MajoorError, match="is gone"):
        module.MajoorHeldImage.execute(tokens[0])
    module.hold("x", "p1")
    server.last_prompt_id = "p2"
    module.hold("y")
    assert list(module.HELD) == ["p2"]  # what the last prompt left is dropped, never mid-prompt
    for _ in range(100):
        module.hold("z")
    assert len(module.HELD["p2"]) == 101  # no eviction inside a prompt


def test_a_ledger_can_be_reset_and_leaves_no_file(tmp_path):
    ledger = cost_guard.Ledger(tmp_path / "l.json")
    ledger.charge("key:a", 5, 0)
    assert (tmp_path / "l.json").is_file()
    ledger.reset("key:a")
    assert not (tmp_path / "l.json").exists() and ledger.spent("key:a") == (0.0, 0.0)


def test_a_damaged_or_old_ledger_file_is_a_fresh_ledger(tmp_path):
    (tmp_path / "l.json").write_text("{not json", encoding="utf-8")
    assert cost_guard.Ledger(tmp_path / "l.json").runs == {}
    (tmp_path / "l.json").write_text('{"runs": {"key:old": {"seconds": 99, "usd": 1, "at": 0}}}', encoding="utf-8")
    assert cost_guard.Ledger(tmp_path / "l.json").runs == {}
