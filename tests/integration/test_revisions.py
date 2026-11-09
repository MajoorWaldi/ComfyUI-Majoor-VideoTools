

def test_a_take_carries_the_graph_that_made_it(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from majoor_videotools.core.workflow_tags import workflow_tags

    hidden = SimpleNamespace(prompt={"1": {"class_type": "X"}}, extra_pnginfo={"workflow": {"nodes": []}})
    video = SimpleNamespace(get_stream_source=lambda: str(tmp_path / "outside" / "a.mp4"))
    assert set(workflow_tags(hidden, video, tmp_path / "project")) == {"prompt", "workflow"}
    assert workflow_tags(SimpleNamespace(prompt=None, extra_pnginfo=None), video, tmp_path / "project") is None
    assert workflow_tags(hidden, SimpleNamespace(get_stream_source=lambda: str(tmp_path / "project" / "x.mp4")), tmp_path / "project") is None  # a stored take handed back
    monkeypatch.setenv("MAJOOR_EMBED_WORKFLOW", "0")
    assert workflow_tags(hidden, video, tmp_path / "project") is None
