import numpy as np
import pytest

from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.motion_library import TEMPLATES, expand_rows
from majoor_videotools.core.music_structure import drop_times, find_downbeats, track_sections
from majoor_videotools.core.profiles import list_profiles, profile_text
from majoor_videotools.core.sync_score import sync_score
from majoor_videotools.core.words import align_lyrics, mark_accents, parse_words, phrase_groups, word_offsets

RATE = 8000


def test_parse_words_accepts_a_list_or_an_object_and_rejects_bad_times():
    rows = [{"word": "one", "start": 0, "end": .4}, {"word": "two", "start": .5, "end": .9}]
    assert parse_words({"words": rows}) == parse_words(rows) == [{"word": "one", "start": 0.0, "end": .4}, {"word": "two", "start": .5, "end": .9}]
    for bad in ([], [{"word": " ", "start": 0, "end": 1}], [{"word": "x", "start": -1, "end": 1}]):  # nothing that can be timed
        with pytest.raises(MajoorError):
            parse_words(bad)
    mixed = parse_words([{"word": "y", "start": .5, "end": 3}, {"word": "x", "start": 0, "end": 0}, {"word": "bad", "start": "a", "end": 1}])  # out of order, no length, no time
    assert [w["word"] for w in mixed] == ["x", "y"] and mixed[0]["end"] > mixed[0]["start"]


def test_lyrics_are_spread_over_the_phrases_and_never_in_the_pauses():
    words = align_lyrics("aa bb cc dd", [(0.0, 2.0), (4.0, 6.0)])
    assert [w["word"] for w in words] == ["aa", "bb", "cc", "dd"]
    assert words[0]["start"] == 0.0 and words[-1]["end"] == 6.0
    assert all(not (2.0 < w["start"] < 4.0) and not (2.0 < w["end"] < 4.0) for w in words)
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(words, words[1:]))
    with pytest.raises(MajoorError):
        align_lyrics("", [(0, 1)])


def test_word_groups_accents_and_offsets():
    words = parse_words([{"word": "a", "start": 1, "end": 1.3}, {"word": "b", "start": 1.4, "end": 1.8}, {"word": "c", "start": 3, "end": 3.4}])
    assert phrase_groups(words) == [(1.0, 1.8), (3.0, 3.4)]
    assert [w["accent"] for w in mark_accents(words, [1.45, 9])] == [False, True, False]
    assert word_offsets(words, 1.2) == [0.0, .2, 1.8]


def _track():
    rng = np.random.default_rng(1)
    parts = [(0.08, 6), (0.4, 6), (1.0, 8), (0.1, 6), (0.5, 4)]
    return np.concatenate([rng.uniform(-a, a, int(s * RATE)) for a, s in parts]).astype(np.float32)


def test_sections_find_intro_drop_and_break():
    sections = track_sections(_track(), RATE)
    tags = [s["tag"] for s in sections]
    assert tags[0] == "intro" and "drop" in tags and "break" in tags
    assert sections[0]["start"] == 0.0 and abs(sections[-1]["end"] - 30.0) < .6
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(sections, sections[1:]))
    assert drop_times(sections) and 10 <= drop_times(sections)[0] <= 14


def test_downbeats_pick_the_loudest_phase():
    samples = np.zeros(RATE * 8, dtype=np.float32)
    beats = [i * .5 for i in range(16)]
    for i, b in enumerate(beats):
        samples[int(b * RATE):int(b * RATE) + 400] = (1.0 if i % 4 == 2 else .3) * np.sin(np.arange(400) / 8)
    assert find_downbeats(samples, RATE, beats) == beats[2::4]


def test_templates_expand_into_ordinary_layers_and_unknown_ones_are_refused():
    rows = expand_rows([{"type": "box", "rect": [0, 0, .5, .5]}, {"template": "end_card", "start": 5, "end": 8, "title": "NIGHT", "credit": "by me"}])
    assert rows[0]["type"] == "box" and [r["content"] for r in rows[1:]] == ["NIGHT", "by me"]
    assert set(TEMPLATES) >= {"end_card", "rec_hud", "caption_mono", "punch_word", "kinetic_lyrics"}
    with pytest.raises(MajoorError):
        expand_rows([{"template": "nope"}])
    with pytest.raises(MajoorError):
        expand_rows([{"template": "punch_word", "start": 0}])
    lyrics = expand_rows([{"template": "kinetic_lyrics", "start": 0, "end": 5, "words": mark_accents(parse_words([{"word": "hey", "start": 1, "end": 1.4}]), [1.0])}])
    assert lyrics[0]["size"] == .11 and lyrics[0]["color"] == "#ffd60a"


def test_the_recipe_profiles_load():
    for name in ("kinetic_lyrics", "punch_text_anime", "editorial_layouts", "camera_rec_hud", "cutout_collage", "lipsync_rap", "brand_film_noir"):
        assert name in list_profiles() and profile_text(name)


def test_sync_score_counts_events_near_an_accent():
    result = sync_score([1.0, 2.1, 5.0], [1.05, 2.0, 3.0])
    assert result == {"events": 3, "mean_offset": round((.05 + .1 + 2.0) / 3, 3), "within": round(2 / 3, 3), "score": 67}
    assert sync_score([], [1])["score"] is None


def test_new_animations_word_times_and_beat_effects_parse_as_layers():
    import json
    from majoor_videotools.core.motion import parse_layers
    rows = [{"type": "text", "content": "ONE TWO", "animation": a, "word_times": [0, .5]} for a in ("blur_in", "scramble", "karaoke_fill", "split_letters")]
    rows += expand_rows([{"template": "flash_hit", "start": 1}, {"template": "whip_wipe", "start": 2}, {"template": "letterbox", "start": 0, "end": 5}, {"template": "polaroid_frame", "start": 0, "end": 5}])
    layers = parse_layers(json.dumps(rows), 6)
    assert [l["animation"] for l in layers[:4]] == ["blur_in", "scramble", "karaoke_fill", "split_letters"] and layers[0]["word_times"] == [0.0, .5]
    assert [l["kind"] for l in layers[4:]] == ["flash", "wipe", "letterbox", "frame"]
    for bad in ([1, 0], [-1], "x", [float("nan")]):  # word timing that cannot be read is no word timing: the text still shows
        assert "word_times" not in parse_layers(json.dumps([{"type": "text", "content": "A", "word_times": bad}]), 6)[0]


def test_beat_effects_draw_in_the_frame_renderer():
    import json
    import numpy as np
    from majoor_videotools.core.motion import _effect, parse_layers
    rows = expand_rows([{"template": "flash_hit", "start": 0}, {"template": "letterbox", "start": 0, "end": 5}, {"template": "polaroid_frame", "start": 0, "end": 5}])
    flash, box, frame_layer = parse_layers(json.dumps(rows), 6)
    state = {"alpha": 1.0}
    image = np.zeros((100, 100, 3), np.uint8)
    _effect(image, flash, state, 0.0, 0, None)
    assert image.min() > 200
    image = np.full((100, 100, 3), 255, np.uint8)
    _effect(image, box, state, 1.0, 0, None)
    assert image[:12].max() == 0 and image[50, 50].min() == 255
    image = np.full((100, 100, 3), 0, np.uint8)
    _effect(image, frame_layer, state, 1.0, 0, None)
    assert image[0, 50].min() > 200 and image[50, 50].max() == 0


def test_text_events_are_placed_in_the_edit_and_scored():
    from majoor_videotools.core.edit_report import text_events
    manifest = {"shots": [{"target_duration_seconds": 2.0, "plan": {"motion": [{"type": "text", "start": .5}, {"type": "box", "start": 1}, {"type": "text", "start": "40%"}]}},
                          {"target_duration_seconds": 3.0, "plan": {"motion": [{"type": "text", "start": 1.0}]}}]}
    assert text_events(manifest) == [.5, 3.0]
    assert sync_score(text_events(manifest), [.55, 3.4])["within"] == .5


def test_layouts_rearrange_the_picture_in_the_frame_renderer():
    import json
    from majoor_videotools.core.motion import _effect, parse_layers
    rows = expand_rows([{"template": t, "start": 0, "end": 2} for t in ("split_stack", "split_diagonal", "circle_mask", "picture_in_picture", "zoom_punch", "cutout_echo")])
    layers = parse_layers(json.dumps(rows), 3)
    assert [l.get("kind", l["type"]) for l in layers] == ["split_stack", "split_diagonal", "circle_mask", "pip", "zoom_punch", "echo", "outline"]
    assert layers[5]["target"] == "background" and layers[5]["needs_mask"] and layers[6]["needs_mask"]
    gradient = np.tile(np.linspace(0, 255, 120, dtype=np.uint8)[None, :, None], (90, 1, 3))
    subject = np.zeros((90, 120), np.float32)
    subject[30:60, 40:80] = 1
    for layer in layers[:6]:
        image = gradient.copy()
        _effect(image, layer, {"alpha": 1.0}, 1.0, 0, subject)
        assert image.shape == gradient.shape and (image != gradient).any(), layer["kind"]
    image = gradient.copy()
    _effect(image, layers[2], {"alpha": 1.0}, 1.0, 0, subject)
    assert image[0, 0].max() == 0 and (image[45, 60] == gradient[45, 60]).all()


def test_templates_work_in_shot_plans_and_keep_their_shot():
    import json
    from majoor_videotools.core.motion_timing import shot_layers
    timeline = json.dumps([{"id": "SHOT_001", "start": 0, "duration": 2}, {"id": "SHOT_002", "start": 2, "duration": 2}])
    rows, _ = shot_layers(json.dumps([{"template": "flash_hit", "start": .5, "shot_id": "SHOT_002"}]), timeline, 4.0, 24.0)
    assert rows[0]["kind"] == "flash" and rows[0]["start"] == pytest.approx(2.5)


def test_new_animations_show_up_in_the_frame_renderer():
    from majoor_videotools.core.motion import _state
    base = {"start": 0.0, "end": 2.0, "in_time": .5, "opacity": 1.0, "out": "none"}
    assert _state({**base, "animation": "scale_pop"}, .05, 2, 0)["scale"] < .6
    assert _state({**base, "animation": "blur_in"}, .1, 2, 0)["alpha"] < 1
    assert _state({**base, "animation": "wiggle"}, .4, 2, 0)["dx"] != 0
    for animation in ("mask_reveal", "scramble", "split_letters", "karaoke_fill"):
        assert _state({**base, "animation": animation}, .25, 2, 0)["reveal"] == .5


def test_lottie_names_are_an_allowlist_and_fonts_are_known():
    import json
    from majoor_videotools.core.motion import FONTS, lottie_names, parse_layers
    assert {"burst", "sparkle"} <= set(lottie_names())
    layer = parse_layers(json.dumps(expand_rows([{"template": "sticker", "start": 0, "end": 1, "name": "burst"}])), 2)[0]
    assert layer["type"] == "lottie" and layer["name"] == "burst" and layer["loop"] is True
    for name in ("../../secret", "nope", ""):  # never a path: the layer is left out, said, and nothing is read
        skipped = []
        assert parse_layers(json.dumps([{"type": "lottie", "name": name}]), 2, skipped) == [] and "unknown lottie" in skipped[0]
    assert 8 <= len(FONTS) <= 12
    assert parse_layers(json.dumps([{"type": "text", "content": "A", "font": "league"}]), 2)[0]["font"] == "league"


def test_tiles_particles_and_text_behind_the_subject():
    import json
    from majoor_videotools.core.motion import _Sprites, _effect, draw_layers, needs_mask, parse_layers
    rows = expand_rows([{"template": "tiles_grid", "start": 0, "end": 2}, {"template": "particles", "start": 0, "end": 2, "count": 30}, {"template": "title_behind", "start": 0, "end": 2, "title": "night"}])
    tiles, spark, title = parse_layers(json.dumps(rows), 3)
    assert spark["count"] == 30 and title["behind"] and title["needs_mask"] and needs_mask([title]) and not needs_mask([tiles, spark])
    gradient = np.tile(np.linspace(0, 255, 120, dtype=np.uint8)[None, :, None], (90, 1, 3))
    image = gradient.copy()
    _effect(image, tiles, {"alpha": 1.0}, 1.0, 0, None)
    assert (image[:45, :60] == image[45:, 60:]).all() and (image != gradient).any()
    image = np.zeros((90, 120, 3), np.uint8)
    _effect(image, spark, {"alpha": 1.0}, 1.0, 0, None)
    first = image.copy()
    assert first.any()
    image[:] = 0
    _effect(image, spark, {"alpha": 1.0}, 1.0, 0, None)
    assert (image == first).all()
    subject = np.zeros((90, 120), np.float32)
    subject[:, 40:80] = 1
    canvas = np.full((90, 120, 3), 120, np.uint8)
    draw_layers(canvas, [title], 1.0, 3.0, 0, _Sprites(120, 90), subject)
    assert (canvas[:, 40:80] == 120).all() and (canvas != 120).any()


def test_lyrics_words_leave_when_the_next_one_comes():
    words = mark_accents(parse_words([{"word": "a", "start": 0, "end": .4}, {"word": "b", "start": .5, "end": .9}, {"word": "c", "start": 3, "end": 3.4}]), [])
    rows = expand_rows([{"template": "kinetic_lyrics", "start": 0, "end": 9, "words": words}])
    assert [(r["content"], r["start"], r["end"]) for r in rows] == [("a", 0, .5), ("b", .5, 3), ("c", 3, pytest.approx(3.7))]
