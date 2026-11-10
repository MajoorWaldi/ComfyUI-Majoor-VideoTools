import pytest

from majoor_videotools.core.api_request import build_request
from majoor_videotools.core.errors import MajoorError

BASE = dict(prompt="A slow orbit around the bottle.", seconds=5.4, aspect="9:16", resolution="720p", seed=7)


def test_seedance_flattens_the_dynamic_combo_and_numbers_the_references():
    r = build_request("seedance_2_5", **BASE, images=["I1", "I2"], audios=["A1"])
    assert r.class_type == "ByteDance2ReferenceNodeV2"
    assert r.inputs["model"] == "Seedance 2.5" and r.inputs["model.duration"] == 6  # 5.4 s is asked as 6: a take shorter than its shot cannot be cut to it
    assert r.inputs["model.ratio"] == "9:16" and r.inputs["model.resolution"] == "720p" and r.inputs["model.task_type"] == "reference"
    assert (r.inputs["model.reference_images.image_1"], r.inputs["model.reference_images.image_2"]) == ("I1", "I2")
    assert r.inputs["model.reference_audios.audio_1"] == "A1" and "model.reference_videos.video_1" not in r.inputs


def test_seedance_needs_a_picture_or_a_video():
    with pytest.raises(MajoorError, match="reference"):
        build_request("seedance_2_5", **BASE)


def test_wan_uses_its_own_spelling():
    r = build_request("wan_3_0", **BASE, images=["I1"], videos=["V1"])
    assert r.class_type == "Wan3ReferenceToVideoApi"
    assert r.inputs["model"] == "wan3.0-video" and r.inputs["model.resolution"] == "720P" and r.inputs["model.duration"] == "6"
    assert r.inputs["model.reference_images.image1"] == "I1" and r.inputs["model.reference_videos.video1"] == "V1"


def test_references_beyond_the_limit_are_left_out_and_said():
    r = build_request("wan_3_0", **BASE, images=[f"I{i}" for i in range(12)])
    assert "model.reference_images.image10" in r.inputs and "model.reference_images.image11" not in r.inputs
    assert "takes 10 reference images" in r.notes[0]


def test_ltx_starts_from_the_first_picture_or_from_text():
    r = build_request("ltx_2_5_pro", **{**BASE, "resolution": "1080p"}, images=["I1", "I2"], videos=["V1"], fps=24)
    assert r.class_type == "LtxApi25ImageToVideo" and r.inputs["image"] == "I1" and r.inputs["model.resolution"] == "1080x1920"
    assert r.inputs["model"] == "LTX-2.5 (Pro)" and r.inputs["model.fps"] == "24" and r.video_fps == 24.0
    assert any("takes 1 reference images" in n for n in r.notes) and any("takes 0 reference videos" in n for n in r.notes)
    assert build_request("ltx_2_5_fast", **BASE).class_type == "LtxApi25TextToVideo"


def test_ltx_refuses_a_format_it_does_not_make():
    with pytest.raises(MajoorError, match="16:9 and 9:16"):
        build_request("ltx_2_5_fast", **{**BASE, "aspect": "1:1"})


def test_local_models_and_bad_settings_are_refused():
    with pytest.raises(MajoorError, match="not an API"):
        build_request("minimax_h3", **BASE)
    with pytest.raises(MajoorError):
        build_request("seedance_2_5", **{**BASE, "prompt": " "}, images=["I"])
    with pytest.raises(MajoorError):
        build_request("seedance_2_5", **{**BASE, "aspect": "2:1"}, images=["I"])


def test_seedance_edits_the_source_video_for_a_remix():
    r = build_request("seedance_2_5", **BASE, images=["I1"], videos=["SRC", "OTHER"], task="edit")
    assert r.inputs["model.task_type"] == "edit" and r.inputs["model.reference_videos.video_1"] == "SRC" and "model.reference_videos.video_2" not in r.inputs
    assert r.inputs["model.reference_images.image_1"] == "I1" and any("keeps the length" in n for n in r.notes)


def test_an_edit_needs_the_source_video_and_a_model_that_edits():
    with pytest.raises(MajoorError, match="source video"):
        build_request("seedance_2_5", **BASE, images=["I1"], task="edit")
    for model in ("wan_3_0", "ltx_2_5_pro"):
        with pytest.raises(MajoorError, match="cannot do the task 'edit'"):
            build_request(model, **BASE, images=["I1"], videos=["SRC"], task="edit")
    with pytest.raises(MajoorError, match="cannot do the task"):
        build_request("seedance_2_5", **BASE, images=["I1"], task="inpaint")


def test_a_source_below_the_minimum_size_is_scaled_up_not_refused():
    for task, videos in (("reference", ["V1"]), ("edit", ["SRC"])):
        assert build_request("seedance_2_5", **BASE, images=["I1"], videos=videos, task=task).inputs["model.auto_upscale"] is True


@pytest.mark.parametrize("model,task", [("seedance_2_5", "reference"), ("seedance_2_5", "edit"), ("wan_3_0", "reference"), ("ltx_2_5_pro", "reference")])
def test_every_request_carries_the_seed_and_what_the_node_needs(model, task):
    r = build_request(model, **BASE, images=["I1"], videos=["SRC"] if task == "edit" else [], task=task)
    assert r.inputs["seed"] == 7 and "model" in r.inputs and "model.duration" in r.inputs  # a key lost from the dict was once hidden by a comment
    if model != "ltx_2_5_pro":
        assert r.inputs["watermark"] is False


def _prompt_of(request):
    return request.inputs.get("model.prompt") or request.inputs["prompt"]


def test_a_prompt_within_the_limit_goes_as_it_is():
    long = "A woman turns her head and the bottle catches the light. " * 70  # about 4,000 characters, 700 words
    request = build_request("seedance_2_5", prompt=long, seconds=6, images=[object()])
    assert _prompt_of(request) == long and not any("characters of prompt" in note for note in request.notes)


def test_a_prompt_over_the_limit_is_cut_at_a_sentence_and_says_so():
    sentence = "A woman turns her head and the bottle catches the light. "
    request = build_request("seedance_2_5", prompt=sentence * 120, seconds=6, images=[object()])  # 6,840 characters, limit 5,000
    prompt = _prompt_of(request)
    assert len(prompt) <= 5000 and prompt.endswith("light.") and any("takes at most 5000 characters" in note for note in request.notes)


def test_every_api_model_states_its_limit_and_the_local_one_has_none():
    from majoor_videotools.core.generators import load_generator
    assert {g: load_generator(g).prompt_max_chars for g in ("seedance_2_5", "wan_3_0", "ltx_2_5_fast", "ltx_2_5_pro", "minimax_h3")} == {
        "seedance_2_5": 5000, "wan_3_0": 20000, "ltx_2_5_fast": 10000, "ltx_2_5_pro": 10000, "minimax_h3": None}


@pytest.mark.parametrize("generator,seconds,asked", [
    ("seedance_2_5", 2.4, 4),   # under the minimum of the model: its minimum, which is what it bills
    ("seedance_2_5", 4.5, 5),   # rounded up, never the banker's round(4.5) = 4
    ("seedance_2_5", 45, 30),   # over its maximum: its maximum
    ("ltx_2_5_fast", 6.5, 8),   # a model with listed lengths: the next one
])
def test_the_seconds_asked_are_whole_and_within_what_the_model_makes(generator, seconds, asked):
    r = build_request(generator, **{**BASE, "seconds": seconds, "aspect": "16:9"}, images=["I1"])
    assert int(r.inputs["model.duration"]) == asked
