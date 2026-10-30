import json
from fractions import Fraction

import numpy as np
import pytest

from majoor_videotools.core.assembler import AssemblyOptions, assemble_shots
from majoor_videotools.core.beats import detect_beats, read_wav_mono, write_wav
from majoor_videotools.core.errors import AssemblyError, MajoorError, ManifestError
from majoor_videotools.core.media_probe import probe
from majoor_videotools.core.models import ShotList
from majoor_videotools.core.paths import ProjectStore
from majoor_videotools.core.revisions import apply_revision, make_metadata, sample_shot_images
from majoor_videotools.core.template import create_template, generation_frames, parse_duration, parse_plan
from majoor_videotools.core.timeline_sources import with_size

PLAN = """```json
{"shots": [
  {"id": "OPEN", "duration": 2, "prompt": "A bottle on obsidian, slow orbit.", "image_prompt": "bottle hero still"},
  {"duration": "36f", "prompt": "Macro push-in on the cap."},
  {"duration": "00:02.5", "prompt": "Pull back to a hero frame.", "notes": "end on logo space"}
]}
```"""


@pytest.fixture
def root(tmp_path):
    return tmp_path / "projects"


def template(root, **kw):
    args = dict(fps=24.0, aspect_ratio="16:9", resolution=320, profile="none")
    return create_template(kw.pop("plan", PLAN), root, **(args | kw))


def click_track(path, bpm, seconds, offset=0.0, rate=22050):
    rng = np.random.default_rng(3)
    x = np.zeros(int(rate * seconds), np.float32)
    for t in np.arange(offset, seconds - 0.1, 60 / bpm):
        i = int(t * rate)
        x[i : i + 800] += (rng.standard_normal(800) * np.exp(-np.arange(800) / 150)).astype(np.float32) * 0.8
    write_wav(path, np.stack([x, x], axis=1), rate)
    return path


def test_duration_formats():
    fps = Fraction(24)
    assert [parse_duration(v, fps) for v in (2, 2.5, "2.5", "2.5s", "60f", "60 frames", "00:02.5", "01:00", "0:0:1")] == [48, 60, 60, 60, 60, 60, 60, 1440, 24]
    with pytest.raises(ValueError):
        parse_duration(None, fps)


def test_h3_generation_grid():
    assert generation_frames(72, "none") == 72
    assert generation_frames(72, "minimax_h3") == 124
    assert generation_frames(124, "minimax_h3") == 124
    assert generation_frames(125, "minimax_h3") == 141  # 17k + 5
    assert generation_frames(360, "minimax_h3") == 362


def test_plan_errors():
    for text, message in (
        ("nope", "not valid JSON"),
        ('{"shots": []}', "non-empty"),
        ('{"shots": [{"duration": 2}, {"id": "SHOT_001", "duration": 2}]}', "duplicate"),
        ('{"shots": [{"id": "a b", "duration": 2}]}', "invalid"),
        ('{"shots": [{"duration": "soon"}]}', "cannot read"),
        ('{"shots": [{"duration": 0}]}', "at least one frame"),
    ):
        with pytest.raises(MajoorError, match=message):
            parse_plan(text, 24, "16:9", 320)
    plan = parse_plan('{"fps": 25, "aspect_ratio": "9:16", "resolution": 640, "shots": [{"duration": 1}]}', 24, "16:9", 320)
    assert (plan.fps, plan.width, plan.height) == (25, 360, 640)


def test_template_is_a_real_shot_list(root):
    sl = template(root, profile="minimax_h3")
    assert [s.shot_id for s in sl.shots] == ["OPEN", "SHOT_002", "SHOT_003"]
    assert [s.frame_count for s in sl.shots] == [48, 36, 60]
    assert sl.source.template and sl.source.frame_count == 144 and sl.source.timing_mode == "CFR"
    assert sl.shots[0].plan["prompt"].startswith("A bottle") and sl.shots[0].plan["image_prompt"] == "bottle hero still"
    assert [s.plan["generation_frames"] for s in sl.shots] == [124, 124, 124]
    assert sl.shots[2].plan["notes"] == "end on logo space" and sl.shots[0].thumbnail_ref
    info = probe(ProjectStore(root, sl.project_id).resolve(sl.source.uri))
    assert info.frame_count == 144 and (info.width, info.height) == (320, 180) and not info.has_audio
    assert ShotList.from_dict(sl.to_dict()) == sl
    assert template(root, profile="minimax_h3") == sl  # same plan, same project, cached


def test_template_carries_music_as_master_audio(root, tmp_path):
    music = click_track(tmp_path / "m.wav", 120, 8)
    sl = template(root, audio_wav=music)
    store = ProjectStore(root, sl.project_id)
    assert sl.source.has_audio and probe(store.resolve(sl.source.uri)).has_audio
    res = assemble_shots(sl, root, AssemblyOptions(missing_shot_policy="use_original"))
    out = probe(res.path)
    assert out.frame_count == 144 and out.has_audio
    assert any("placeholder kept" in w for w in res.warnings)


def test_a_size_in_pixels_replaces_aspect_and_resolution(root):
    plan = '{"shots": [{"duration": 1}, {"duration": 1}]}'
    sl = template(root, plan=with_size(plan, 576, 1024))  # the widgets say 16:9 at 320: the size wins
    assert (sl.source.width, sl.source.height) == (576, 1024)
    odd = template(root, plan=with_size('[{"duration": 1}]', 770, 1345)).source  # a bare list of shots is accepted, the sizes are made even
    assert (odd.width, odd.height) == (770, 1344)
    assert with_size("not json", 576, 1024) == "not json"
    with pytest.raises(MajoorError, match="between 64 and 4096"):
        template(root, plan=with_size(plan, 32, 1024))
    assert template(root, plan=plan).source.width == 320  # without it the aspect and the resolution stay


def test_beats_find_tempo_and_phase(tmp_path):
    for bpm, offset in ((120, 0.13), (96, 0.31)):
        samples, rate = read_wav_mono(click_track(tmp_path / f"{bpm}.wav", bpm, 16, offset))
        found, beats = detect_beats(samples, rate)
        period = 60 / bpm
        assert abs(found - bpm) < 1.5
        assert max(abs(((b - offset) + period / 2) % period - period / 2) for b in beats[:8]) < 0.03


def test_the_phase_follows_the_kick_not_the_hats(tmp_path):
    rate, bpm, offset = 44100, 140, 0.21
    period = 60 / bpm
    samples = np.zeros(rate * 10, np.float32)
    for k in range(int(10 / period)):
        t = offset + k * period
        start = int(t * rate)
        n = int(0.12 * rate)
        samples[start:start + n] += (0.6 * np.sin(2 * np.pi * 55 * np.arange(n) / rate) * np.exp(-np.arange(n) / (0.03 * rate)))[: len(samples) - start]  # kick
        for h in (0.5, 0.25, 0.75):  # louder, sharper hats on the off-beats and the sixteenths
            hs = int((t + h * period) * rate)
            samples[hs:hs + 200] += np.random.default_rng(k).uniform(-0.9, 0.9, 200)[: len(samples) - hs]
    found, beats = detect_beats(samples, rate, bpm=bpm)
    assert max(abs(((b - offset) + period / 2) % period - period / 2) for b in beats[:8]) < 0.03


def test_cuts_snap_to_beats(root, tmp_path):
    music = click_track(tmp_path / "m.wav", 120, 8, offset=0.13)  # beats every 12 frames, at frame 3.1 + 12k
    plan = '{"shots": [{"duration_frames": 50}, {"duration_frames": 46}, {"duration_frames": 48}]}'
    plain = template(root, plan=plan, audio_wav=music)
    snapped = template(root, plan=plan, audio_wav=music, cut_snap="beat")
    assert [s.frame_count for s in plain.shots] == [50, 46, 48]
    cuts = [snapped.shots[1].start_frame, snapped.shots[2].start_frame]
    assert all(abs((c - 3.1) % 12) in range(0, 2) or abs((c - 3.1) % 12 - 12) < 1.5 for c in cuts) and cuts != [50, 96]
    assert sum(s.frame_count for s in snapped.shots) == 144
    assert snapped.detection.warnings and "BPM" in snapped.detection.warnings[0]
    assert snapped.project_id != plain.project_id
    bars = template(root, plan=plan, audio_wav=music, cut_snap="bar")
    assert all((s.start_frame - 3) % 48 in (0, 1, 2, 47) for s in bars.shots[1:])


def test_replace_template_shots_and_reassemble(root, fixtures):
    sl = template(root)
    with pytest.raises(AssemblyError, match="template placeholder"):
        assemble_shots(sl, root, AssemblyOptions())
    shot = sl.get_shot("SHOT_002")
    updated = apply_revision(sl, root, make_metadata(sl, shot, shot.active), fixtures["gen"])
    with pytest.raises(AssemblyError, match=r"1 of 3 shots.*with a take: SHOT_002; without: OPEN, SHOT_003.*previous one"):  # says which shots are missing and why
        assemble_shots(updated, root, AssemblyOptions())
    both = apply_revision(updated, root, make_metadata(updated, updated.get_shot("OPEN"), updated.get_shot("OPEN").active), fixtures["gen_short"])
    res = assemble_shots(both, root, AssemblyOptions(missing_shot_policy="use_original", audio_policy="mute"))
    assert probe(res.path).frame_count == 144 and len(res.warnings) >= 1
    third = both.get_shot("SHOT_003")
    full = apply_revision(both, root, make_metadata(both, third, third.active), fixtures["gen"])
    done = assemble_shots(full, root, AssemblyOptions(audio_policy="mute"))
    assert probe(done.path).frame_count == 144 and done.modified_count == 3


def test_regenerating_a_shot_from_a_cached_list_keeps_the_other_takes(root, fixtures):
    sl = template(root)
    take = lambda lst, sid, video: apply_revision(lst, root, make_metadata(lst, lst.get_shot(sid), lst.get_shot(sid).active), video)
    first = take(sl, "SHOT_002", fixtures["gen"])
    both = take(first, "SHOT_003", fixtures["gen"])
    # the second run of a chain only re-executes the shot being regenerated: its list is the cached one, without the other takes
    again = take(sl, "SHOT_002", fixtures["gen_short"])
    assert [r.revision_id for r in again.get_shot("SHOT_002").revisions] == ["original", "take_001", "take_002"]
    assert again.get_shot("SHOT_002").active_revision_id == "take_002"
    assert [r.revision_id for r in again.get_shot("SHOT_003").revisions] == [r.revision_id for r in both.get_shot("SHOT_003").revisions]
    assert ShotList.from_dict(ProjectStore(root, sl.project_id).read_json("manifest.json")) == again
    assert take(sl, "SHOT_002", fixtures["gen_short"]) == again  # the same generation again is not a new take


def test_continue_from_previous_shot(root, fixtures):
    sl = template(root)
    store = ProjectStore(root, sl.project_id)
    first, second = sl.get_shot("OPEN"), sl.get_shot("SHOT_002")
    with pytest.raises(ManifestError, match="no generated take yet"):
        sample_shot_images(store, sl, second, second.active, "first", 1, 128, from_previous=True)
    own = sample_shot_images(store, sl, first, first.active, "first", 1, 128, from_previous=True)  # first shot: nothing to continue from
    assert own.shape[0] == 1
    updated = apply_revision(sl, root, make_metadata(sl, first, first.active), fixtures["gen"])
    frames = sample_shot_images(store, updated, second, second.active, "first", 1, 128, from_previous=True)
    last_of_take = sample_shot_images(store, updated, updated.get_shot("OPEN"), updated.get_shot("OPEN").active, "last", 1, 128)
    assert frames.shape == last_of_take.shape and np.array_equal(frames, last_of_take)


LAYERED = """{"aspect_ratio": "16:9", "shots": [
  {"id": "YELLOW", "duration": 2, "color": "yellow", "prompt": "Split screen over a yellow ground.",
   "layers": [{"layout": "left", "color": "#2255ff"},
              {"rect": [0.55, 0.1, 0.35, 0.5], "color": "red", "opacity": 0.5}]},
  {"id": "BLUE", "duration": 1.5, "color": "#0033aa"},
  {"id": "AUTO", "duration": 1.5}
]}"""


def test_colored_shots_and_layers(root):
    from majoor_videotools.core.template import _slate

    plan = parse_plan(LAYERED, 24, "16:9", 320)
    assert plan.shots[0].color == "yellow" and len(plan.shots[0].layers) == 2 and plan.shots[0].layers[1].rect == (0.55, 0.1, 0.35, 0.5)
    yellow = _slate(plan, plan.shots[0], (1, 2, 3))
    w, h = yellow.size
    assert yellow.getpixel((w - 4, h - 4)) == (255, 255, 0)  # background
    assert yellow.getpixel((w // 4, h // 2)) == (34, 85, 255)  # left card
    mixed = yellow.getpixel((int(w * 0.7), int(h * 0.3)))  # red at 50 % over yellow
    assert mixed[0] == 255 and 120 < mixed[1] < 135 and mixed[2] == 0
    assert _slate(plan, plan.shots[1], (1, 2, 3)).getpixel((5, 5)) == (0, 51, 170)
    assert _slate(plan, plan.shots[2], (9, 8, 7)).getpixel((5, 5)) == (9, 8, 7)  # no color: automatic tint

    sl = template(root, plan=LAYERED)
    assert [s.shot_id for s in sl.shots] == ["YELLOW", "BLUE", "AUTO"] and sl.source.frame_count == 120


def test_layer_errors():
    for text, message in (
        ('{"shots": [{"duration": 1, "layers": [{"layout": "diagonal"}]}]}', "unknown layout"),
        ('{"shots": [{"duration": 1, "layers": [{"rect": [0.6, 0, 0.6, 1]}]}]}', "inside the frame"),
        ('{"shots": [{"duration": 1, "layers": [{"rect": "full"}]}]}', "rect must be"),
        ('{"shots": [{"duration": 1, "layers": "left"}]}', "must be a list"),
    ):
        with pytest.raises(MajoorError, match=message):
            parse_plan(text, 24, "16:9", 320)


def test_v1_planner_prompt_example_is_a_valid_15s_plan():
    from pathlib import Path

    examples = Path(__file__).resolve().parents[2] / "examples"
    example = (examples / "timeline_aura_farming.json").read_text(encoding="utf-8")
    assert example.strip() in (examples / "prompts" / "timeline_planner_v1.txt").read_text(encoding="utf-8")
    plan = parse_plan(example, 24, "16:9", 320)
    assert len(plan.shots) == 9 and sum(s.frames for s in plan.shots) == 360 and not any(s.fx for s in plan.shots)


def test_planner_prompt_example_is_a_valid_dense_8s_plan():
    from pathlib import Path

    examples = Path(__file__).resolve().parents[2] / "examples"
    example = (examples / "timeline_fashion_motion.json").read_text(encoding="utf-8")
    plan = parse_plan(example, 24, "16:9", 320)
    assert plan.fps == 24 and (plan.width, plan.height) == (180, 320) and len(plan.shots) == 7
    assert sum(s.frames for s in plan.shots) == 192 and all(s.prompt and s.image_prompt for s in plan.shots)
    for shot in plan.shots:  # sub-cuts add up to their shot
        subs = shot.fx.get("sub_cuts")
        assert not subs or sum(c["weight"] for c in subs) == shot.frames, shot.shot_id
    cuts = sum(len(s.fx.get("sub_cuts", [1])) for s in plan.shots)
    assert cuts / 8 >= 2.5 and min(c["weight"] for s in plan.shots for c in s.fx.get("sub_cuts", [])) >= 6


def test_a_plan_that_would_hang_or_crash_ffmpeg_is_refused_with_a_clear_message():
    one = {"duration": 2, "prompt": "a"}
    for plan, message in (
        ({"shots": [one] * 151}, "at most 150"),
        ({"shots": [{"duration": 1e9}]}, "longer than 60 minutes"),
        ({"fps": 1e9, "shots": [one]}, "fps must be between 1 and 240"),
        ({"fps": "fast", "shots": [one]}, "fps 'fast' is not a number"),
        ({"resolution": 10**9, "shots": [one]}, "between 64 and 4096"),
        ({"resolution": "big", "shots": [one]}, "resolution 'big' is not a number"),
    ):
        with pytest.raises(MajoorError, match=message):
            parse_plan(json.dumps(plan), 24, "16:9", 320)
    assert len(parse_plan(json.dumps({"shots": [one] * 150}), 24, "16:9", 320).shots) == 150


def test_plan_reading_tolerates_common_llm_variants():
    shots = [{"duration": 2, "prompt": "a"}, {"seconds": "1.5", "video_prompt": "b"}]
    for text in (json.dumps(shots), json.dumps({"timeline": shots}), json.dumps({"plan": {"title": "t", "shots": shots}}), "Here is the plan: " + json.dumps({"shots": shots}) + " Enjoy!"):
        plan = parse_plan(text, 24, "16:9", 320)
        assert [s.frames for s in plan.shots] == [48, 36] and [s.prompt for s in plan.shots] == ["a", "b"]


def test_plan_errors_show_what_was_received():
    with pytest.raises(MajoorError, match="received: 'REFERENCE ROLES: one line each"):
        parse_plan("REFERENCE ROLES: one line each for the pictures", 24, "16:9", 320)
    with pytest.raises(MajoorError, match=r"non-empty .shots. list. The node received: '\{\"hello\""):
        parse_plan('{"hello": "world"}', 24, "16:9", 320)


FX_PLAN = """{"fps": 24, "aspect_ratio": "9:16", "shots": [
  {"id": "BURST", "prompt": "a", "zoom": [1, 1.4], "transition": "flash", "text": {"content": "dxxx", "position": "bottom_left", "background": "black", "repeat": 2},
   "sub_cuts": [{"duration": 0.25}, {"duration": 0.25, "zoom": 2, "flip": true, "transition": "whip"},
                {"duration": 0.5, "look": "mono", "speed_ramp": [1, 3]}, {"duration": 0.5, "zoom": [2.5, 1], "transition": "punch", "start": 1.0}]},
  {"id": "RAMP", "duration": 1.0, "prompt": "b", "speed_ramp": [0.5, 3], "look": "contrast", "transition": {"type": "whip_v", "frames": 6}}
]}"""


def test_split_frames_is_proportional_with_a_floor():
    from majoor_videotools.core.fx import split_frames

    assert split_frames(36, [6, 6, 12, 12]) == [6, 6, 12, 12]
    assert sum(split_frames(10, [1, 1, 1], 3)) == 10 and min(split_frames(10, [1, 1, 1], 3)) == 3
    assert split_frames(7, [1, 20], 3) == [3, 4]
    assert split_frames(2, [1, 1, 1]) == [1, 1]  # more cuts than frames: the extra ones are dropped


def test_fx_fields_are_parsed_and_stored(root):
    plan = parse_plan(FX_PLAN, 24, "16:9", 320)
    burst = plan.shots[0]
    assert burst.frames == 36  # no duration: the sub-cuts make it
    assert burst.fx["zoom"] == [1.0, 1.4] and burst.fx["transition"] == {"type": "flash", "frames": 4}
    assert [c["weight"] for c in burst.fx["sub_cuts"]] == [6, 6, 12, 12] and burst.fx["sub_cuts"][3]["start"] == 1.0
    assert plan.shots[1].fx["transition"] == {"type": "whip_v", "frames": 6}
    sl = template(root, plan=FX_PLAN)
    fx = sl.get_shot("BURST").plan["fx"]
    assert [c["frames"] for c in fx["sub_cuts"]] == [6, 6, 12, 12] and "weight" not in fx["sub_cuts"][0]
    assert ShotList.from_dict(sl.to_dict()) == sl and "fx" not in (template(root).shots[0].plan or {})


def test_effect_values_out_of_range_are_clamped():
    plan = parse_plan('{"shots": [{"duration": 1, "speed": 20, "zoom": [0.5, 9], "sub_cuts": [{"duration": 0.5, "zoom": 0.8}, {"duration": 0.5, "focus": [-1, 2]}]}]}', 24, "16:9", 512)
    fx = plan.shots[0].fx
    assert fx["speed"] == 8.0 and fx["zoom"] == [1.0, 4.0]
    assert fx["sub_cuts"][0]["zoom"] == [1.0, 1.0] and fx["sub_cuts"][1]["focus"] == [0.0, 1.0]


def test_fx_errors():
    for text, message in (
        ('{"shots": [{"duration": 1, "look": "sepia"}]}', "unknown look"),
        ('{"shots": [{"duration": 1, "speed_ramp": 2}]}', "speed_ramp must be"),
        ('{"shots": [{"duration": 1, "sub_cuts": []}]}', "non-empty list"),
        ('{"shots": [{"duration": 1, "sub_cuts": [{"duration": 0}]}]}', "at least one frame"),
        ('{"shots": [{"duration": 1, "sub_cuts": [{"zoom": 2}]}]}', "cannot read the duration"),
        ('{"shots": [{"duration": 1, "text": {"content": "x", "position": "nowhere"}}]}', "unknown text position"),
    ):
        with pytest.raises(MajoorError, match=message):
            parse_plan(text, 24, "16:9", 320)


def test_effects_are_rendered_by_the_assembler(root, fixtures):
    sl = template(root, plan=FX_PLAN)
    for sid in ("BURST", "RAMP"):
        shot = sl.get_shot(sid)
        sl = apply_revision(sl, root, make_metadata(sl, shot, shot.active), fixtures["gen"])  # 5 s take at 30 fps
    res = assemble_shots(sl, root, AssemblyOptions(audio_policy="mute"))
    out = probe(res.path)
    assert out.frame_count == 60 and (out.width, out.height) == (sl.source.width, sl.source.height)
    assert res.timeline == [("BURST", "take_001", 1.5), ("RAMP", "take_001", 1.0)]  # sub-cuts do not split the shot
    assert res.shot_count == 2 and res.modified_count == 2 and not res.warnings
    assert any((ProjectStore(root, sl.project_id).resolve("cache/text")).glob("*.png"))
    again = assemble_shots(sl, root, AssemblyOptions(audio_policy="mute"))
    assert again.reused and again.path == res.path


def test_sub_cuts_and_cuts_snap_to_half_beats(root, tmp_path):
    music = click_track(tmp_path / "m.wav", 120, 8, offset=0.13)  # a beat every 12 frames at 3.1 + 12k, an offbeat every 6
    plan = '{"shots": [{"duration_frames": 48, "sub_cuts": [{"duration_frames": 10}, {"duration_frames": 14}, {"duration_frames": 24}]}, {"duration_frames": 96}]}'
    sl = template(root, plan=plan, audio_wav=music, cut_snap="half_beat")
    assert sum(s.frame_count for s in sl.shots) == 144
    cuts = np.cumsum([c["frames"] for c in sl.shots[0].plan["fx"]["sub_cuts"]])[:-1] + sl.shots[0].start_frame
    assert all(abs(((c - 3.1) + 3) % 6 - 3) < 1.5 for c in cuts), cuts


def test_plan_from_music_cuts_on_the_bars_and_beats(root, tmp_path):
    from majoor_videotools.core.timeline_sources import plan_from_music

    samples, rate = read_wav_mono(click_track(tmp_path / "m.wav", 120, 8, offset=0.13))  # beats every 12 frames from frame 3.1
    plan, info = plan_from_music(samples, rate, cut_every="bar", fps=24)
    lengths = [s["duration_frames"] for s in plan["shots"]]
    assert abs(info["bpm"] - 120) < 1.5 and sum(lengths) == 192 and len(lengths) == 4 and lengths[1:3] == [48, 48]
    assert plan["shots"][1]["notes"].startswith("bar 2")
    half, _ = plan_from_music(samples, rate, cut_every="half_beat", fps=24)
    assert 28 <= len(half["shots"]) <= 32 and min(s["duration_frames"] for s in half["shots"]) >= 6
    three, detail = plan_from_music(samples, rate, cut_every="beat", shots=3, fps=24)
    assert len(three["shots"]) == 3 and sum(s["duration_frames"] for s in three["shots"]) == 192 and not detail["warnings"]
    short, _ = plan_from_music(samples, rate, cut_every="bar", duration=5, fps=24)
    assert sum(s["duration_frames"] for s in short["shots"]) == 120
    shifted, _ = plan_from_music(samples, rate, cut_every="bar", downbeat=2, fps=24)
    assert [s["duration_frames"] for s in shifted["shots"]][1] == 48 and shifted["shots"][0]["duration_frames"] != plan["shots"][0]["duration_frames"]
    too_many, detail = plan_from_music(samples, rate, cut_every="bar", shots=40, fps=24)
    assert len(too_many["shots"]) == 4 and detail["warnings"]
    with pytest.raises(MajoorError, match="cut_every"):
        plan_from_music(samples, rate, cut_every="triplet")
    sl = template(root, plan=json.dumps(plan), audio_wav=tmp_path / "m.wav")  # the plan is a normal Timeline plan
    assert [s.frame_count for s in sl.shots] == lengths and sl.source.has_audio


def test_cuts_are_grouped_into_shots_with_sub_cuts():
    from majoor_videotools.core.timeline_sources import group_cuts

    assert group_cuts([6, 6, 6, 6, 24, 6], 24) == [[6, 6, 6, 6], [24, 6]]
    assert group_cuts([30, 30], 24) == [[30], [30]]
    assert group_cuts([6, 6], 24) == [[6, 6]]


def test_plan_from_video_keeps_the_rhythm_of_the_reference(tmp_path, monkeypatch):
    import subprocess
    import sys
    import types

    from majoor_videotools.core.timeline_sources import plan_from_video, rhythm_text

    video = tmp_path / "ref.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=432x768:r=24:d=6", "-pix_fmt", "yuv420p", str(video)], check=True)
    fake = types.ModuleType("majoor_videotools.adapters.pyscenedetect")
    fake.detect_cut_times = lambda path, mode, sensitivity, min_frames: [0.25, 0.5, 0.75, 2.0, 2.25, 4.0]
    monkeypatch.setitem(sys.modules, "majoor_videotools.adapters.pyscenedetect", fake)
    monkeypatch.setattr(sys.modules.setdefault("majoor_videotools.adapters", types.ModuleType("majoor_videotools.adapters")), "pyscenedetect", fake, raising=False)  # a real module already imported is an attribute of its package: that wins over sys.modules
    plan, detail = plan_from_video(video, min_shot_seconds=1.0)
    rows = plan["shots"]
    assert detail["aspect_ratio"] == "9:16" and detail["cuts"] == 7 and plan["fps"] == 24
    assert [r["duration_frames"] for r in rows] == [48, 48, 48]  # cuts of 6, 6, 6, 30 | 6, 42 | 48 frames
    assert rows[0]["sub_cuts"] == [{"duration_frames": n} for n in (6, 6, 6, 30)] and "sub_cuts" not in rows[2]
    assert sum(r["duration_frames"] for r in rows) == 144
    text = rhythm_text(json.dumps(plan), 24, "reference.mp4")
    assert text.startswith("EDIT RHYTHM: 3 shots") and "SHOT_001" in text and "cuts: 0.25 / 0.25 / 0.25 / 1.25" in text
    with pytest.raises(MajoorError, match="detection_mode"):
        plan_from_video(video, detection_mode="manual")


SKELETON = json.dumps({"fps": 24, "aspect_ratio": "9:16", "shots": [
    {"duration_frames": 48, "notes": "ref 0-2s", "sub_cuts": [{"duration_frames": 6}, {"duration_frames": 6}, {"duration_frames": 36}]},
    {"duration_frames": 48, "notes": "ref 2-4s"},
    {"duration_frames": 24},
]})
LLM_PLAN = json.dumps({"title": "llm", "fps": 30, "aspect_ratio": "16:9", "shots": [
    {"id": "SHOT_001", "duration": 9, "prompt": "<Picture 1> wide", "image_prompt": "still 1", "zoom": [1, 1.3], "transition": "flash",
     "sub_cuts": [{"duration": 1, "zoom": 2}, {"duration": 1, "flip": True}, {"duration": 1, "look": "mono"}, {"duration": 1}]},
    {"id": "SHOT_002", "duration": 1, "prompt": "<Picture 1> close", "speed": 2,
     "sub_cuts": [{"duration": 0.5, "zoom": 1.5}, {"duration": 0.5, "flip": True}]},
    {"id": "SHOT_003", "duration": 1, "prompt": "<Picture 1> hold", "text": {"content": "hi", "position": "bottom"}},
    {"id": "SHOT_004", "duration": 1, "prompt": "extra"},
]})


def test_merge_keeps_the_rhythm_of_the_skeleton_and_the_prompts_of_the_plan():
    from majoor_videotools.core.timeline_sources import merge_plans

    merged, warnings = merge_plans(SKELETON, LLM_PLAN, 24, "16:9", 768)
    rows = merged["shots"]
    assert [r["duration_frames"] for r in rows] == [48, 48, 24] and merged["aspect_ratio"] == "9:16" and merged["fps"] == 24.0
    assert [r["prompt"] for r in rows] == ["<Picture 1> wide", "<Picture 1> close", "<Picture 1> hold"]
    assert [c["duration_frames"] for c in rows[0]["sub_cuts"]] == [6, 6, 36]  # the cuts of the rhythm, not the plan's four
    assert rows[0]["sub_cuts"][0]["zoom"] == [2.0, 2.0] and rows[0]["sub_cuts"][1]["flip"] is True and rows[0]["sub_cuts"][2]["look"] == "mono"
    assert rows[0]["transition"] == {"type": "flash", "frames": 4} and rows[0]["zoom"] == [1.0, 1.3]
    assert [c["duration_frames"] for c in rows[1]["sub_cuts"]] == [15, 15]  # the rhythm had none: the plan's cuts, as proportions (scaled to the shot when the timeline is made)
    assert rows[2]["text"]["content"] == "hi" and "ref 0-2s" in rows[0]["notes"]
    assert any("4 in the plan" in w for w in warnings) and any("extra ones were ignored" in w for w in warnings)
    plan = parse_plan(json.dumps(merged), 24, "16:9", 320)  # a plan Create Timeline reads again
    assert sum(s.frames for s in plan.shots) == 120 and plan.shots[0].fx["sub_cuts"][1]["flip"] is True and plan.shots[2].fx["text"]["position"] == "bottom"


def test_merge_leaves_shots_without_a_prompt_and_matches_by_position():
    from majoor_videotools.core.timeline_sources import merge_plans

    llm = json.dumps({"shots": [{"prompt": "first"}]})  # no ids: matched by position
    merged, warnings = merge_plans(SKELETON, llm, 24, "16:9", 768)
    assert [r["prompt"] for r in merged["shots"]] == ["first", "", ""] and sum("no shot for it" in w for w in warnings) == 2
    assert merged["shots"][0]["sub_cuts"] == [{"duration_frames": 6}, {"duration_frames": 6}, {"duration_frames": 36}]


def test_effects_and_sub_cuts_can_be_switched_off_at_assembly(root, fixtures):
    sl = template(root, plan=FX_PLAN)
    for sid in ("BURST", "RAMP"):
        shot = sl.get_shot(sid)
        sl = apply_revision(sl, root, make_metadata(sl, shot, shot.active), fixtures["gen"])
    full = assemble_shots(sl, root, AssemblyOptions(audio_policy="mute"))
    plain = assemble_shots(sl, root, AssemblyOptions(audio_policy="mute", effects=False))
    one_piece = assemble_shots(sl, root, AssemblyOptions(audio_policy="mute", sub_cuts=False))
    no_text = assemble_shots(sl, root, AssemblyOptions(audio_policy="mute", text=False))
    assert len({full.path, plain.path, one_piece.path, no_text.path}) == 4  # four different exports of the same takes: the text is its own switch
    assert all(probe(r.path).frame_count == 60 for r in (full, plain, one_piece, no_text))
    assert [t[0] for t in plain.timeline] == ["BURST", "RAMP"] and len(plain.warnings) == 2  # the usual "take trimmed to the target" notes
    assert not full.warnings


def _tone_energy(path, freq):
    import subprocess

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    bin_ = int(freq * len(x) / 48000)
    return float(spectrum[max(bin_ - 3, 0):bin_ + 4].max()), x


def test_the_sound_of_the_takes_is_kept_under_the_music_and_the_cuts_get_effects(root, fixtures, tmp_path):
    sl = template(root, plan=FX_PLAN)
    for sid in ("BURST", "RAMP"):
        shot = sl.get_shot(sid)
        sl = apply_revision(sl, root, make_metadata(sl, shot, shot.active), fixtures["gen"])  # the take has a 880 Hz tone: its "sound design"
    write_wav(tmp_path / "music.wav", np.stack([0.5 * np.sin(2 * np.pi * 110 * np.arange(48000 * 3) / 48000)] * 2, axis=1).astype(np.float32), 48000)
    music = tmp_path / "music.wav"
    shots_only = assemble_shots(sl, root, AssemblyOptions(audio_policy="shot_audio"))
    with_music = assemble_shots(sl, root, AssemblyOptions(audio_policy="shot_audio", music=music))
    ducked = assemble_shots(sl, root, AssemblyOptions(audio_policy="shot_audio", music=music, duck=1.0))
    quiet = assemble_shots(sl, root, AssemblyOptions(audio_policy="shot_audio", music=music, shot_volume=0.0))
    effects = assemble_shots(sl, root, AssemblyOptions(audio_policy="shot_audio", music=music, auto_sfx=True))
    sound_of_shots, _ = _tone_energy(shots_only.path, 880)
    assert sound_of_shots > 50  # the takes keep their sound although the shots are cut in pieces with effects
    music_and_shots = (_tone_energy(with_music.path, 880)[0], _tone_energy(with_music.path, 110)[0])
    assert music_and_shots[0] > 50 and music_and_shots[1] > 50  # both are in the mix
    assert _tone_energy(ducked.path, 110)[0] < 0.7 * music_and_shots[1]  # the music gives way to the takes
    assert _tone_energy(quiet.path, 880)[0] < 0.05 * sound_of_shots and _tone_energy(quiet.path, 110)[0] > 50  # shot_volume 0: only the music is left
    plain, with_effects = _tone_energy(with_music.path, 110)[1], _tone_energy(effects.path, 110)[1]
    assert len({with_music.path, effects.path}) == 2 and float(np.abs(with_effects - plain).max()) > 0.1  # the cuts carry sounds the music does not have


def test_every_cue_of_the_sound_effects_is_a_sound_of_its_own():
    from majoor_videotools.core.sfx import CUES, GAINS, cue_sound, render_track

    kinds = sorted(set(CUES.values()) | {"hit"})
    assert set(kinds) <= set(GAINS)
    sounds = {k: cue_sound(k) for k in kinds}
    assert all(0.05 < len(v) / 48000 < 2.0 and abs(float(np.abs(v).max()) - 1.0) < 1e-6 for v in sounds.values())
    assert all(not np.array_equal(sounds[a][:2000], sounds[b][:2000]) for a in kinds for b in kinds if a < b)
    track = render_track([(0.5, "impact"), (1.2, "whoosh"), (9.0, "hit")], 2.0)  # an event past the end is dropped
    assert track.shape == (96000, 2) and float(np.abs(track[:int(0.49 * 48000)]).max()) == 0.0 and float(np.abs(track[int(0.5 * 48000):int(0.6 * 48000)]).max()) > 0.1
    assert np.array_equal(render_track([(0.5, "impact")], 1.0), render_track([(0.5, "impact")], 1.0))  # the same every time


def test_a_project_is_read_back_with_its_registered_takes(root, fixtures):
    from majoor_videotools.core.project import load_shot_list

    sl = template(root, plan=FX_PLAN)
    assert load_shot_list(root, sl.project_id) == sl  # what Create Timeline wrote
    shot = sl.get_shot("BURST")
    done = apply_revision(sl, root, make_metadata(sl, shot, shot.active), fixtures["gen"])
    back = load_shot_list(root, sl.project_id)
    assert back.get_shot("BURST").active_revision_id == done.get_shot("BURST").active_revision_id != "original"  # the take of a run that ended is in the manifest
    with pytest.raises(MajoorError, match="no manifest"):
        load_shot_list(root, "p_" + "0" * 12)


def test_a_shot_tells_its_transition_and_cuts(root):
    from majoor_videotools.core.fx import describe_fx

    sl = template(root, plan=FX_PLAN)
    burst, ramp = sl.get_shot("BURST"), sl.get_shot("RAMP")
    info, text = describe_fx(burst.plan["fx"], 24.0, burst.frame_count)
    assert info["transition"] == {"type": "flash", "frames": 4, "seconds": 0.167} and info["cut_count"] == 4 and info["duration_s"] == 1.5
    assert [c["duration_s"] for c in info["sub_cuts"]] == [0.25, 0.25, 0.5, 0.5] and info["sub_cuts"][1]["flip"] is True and info["sub_cuts"][1]["transition"]["type"] == "whip"
    assert info["sub_cuts"][3]["start"] == 1.0 and info["zoom"] == [1.0, 1.4] and info["text"]["content"] == "dxxx"
    lines = text.splitlines()
    assert lines[0] == "transition in: flash (4 frames)" and lines[1].startswith("cuts (4): 0.25s / 0.25s (zoom 2, flip, transition whip) / 0.50s (speed 1→3, look mono)")
    assert lines[2] == "shot: zoom 1→1.4, text 'dxxx' (bottom_left)"
    json.dumps(info)  # goes out of the node as text
    info, text = describe_fx(ramp.plan["fx"], 24.0, ramp.frame_count)
    assert info["cut_count"] == 1 and text.splitlines()[:2] == ["transition in: whip_v (6 frames)", "cuts: 1 (the whole shot)"] and "speed 0.5→3" in text and "look contrast" in text
    info, text = describe_fx(None, 24.0, 48)
    assert info["transition"] is None and info["duration_s"] == 2.0 and text == "transition in: cut\ncuts: 1 (the whole shot)"


def test_a_shot_brief_has_its_place_role_transition_and_cuts(root):
    from majoor_videotools.core.fx import describe_shot

    plan = json.dumps({"fps": 24, "shots": [{"id": "SHOT_001", "duration": 1.0, "prompt": "p", "notes": "Hook: full body, then two punch-ins.", "transition": "flash",
                                              "sub_cuts": [{"duration": 0.5}, {"duration": 0.25, "zoom": 1.9}, {"duration": 0.25, "flip": True}]},
                                             {"id": "SHOT_002", "duration": 1.0, "prompt": "q"}]})
    sl = template(root, plan=plan)
    first = sl.get_shot("SHOT_001")
    info, text = describe_shot("SHOT_001", 0.0, 1.0, first.frame_count, first.plan, 24.0)
    assert text.splitlines()[:4] == ["SHOT_001 · 0.00-1.00s · 1.00s · 24 frames", "role: Hook: full body, then two punch-ins.", "transition in: flash (4 frames)", "cuts (3): 0.50s / 0.25s (zoom 1.9) / 0.25s (flip)"]
    assert info["notes"].startswith("Hook") and info["cut_count"] == 3 and info["end_s"] == 1.0 and info["start_s"] == 0.0
    second = sl.get_shot("SHOT_002")
    info, text = describe_shot("SHOT_002", 1.0, 1.0, second.frame_count, second.plan, 24.0)
    assert text == "SHOT_002 · 1.00-2.00s · 1.00s · 24 frames\ntransition in: cut\ncuts: 1 (the whole shot)" and info["notes"] == ""
    info, text = describe_shot("SHOT_003", 4.5, 2.0, 48, None, 24.0)  # a shot cut from a video has no plan
    assert text.splitlines()[0] == "SHOT_003 · 4.50-6.50s · 2.00s · 48 frames" and info["cut_count"] == 1


def test_every_prompt_file_is_listed_and_the_h3_writer_knows_the_format():
    from pathlib import Path

    folder = Path(__file__).resolve().parents[2] / "examples" / "prompts"
    index = (folder / "README.md").read_text(encoding="utf-8")
    for f in folder.glob("*.txt"):
        assert f.name in index or f.name.startswith("timeline_planner_user_request"), f.name
    writer = (folder / "h3_shot_prompt_from_plan.txt").read_text(encoding="utf-8")
    for needed in ("<Picture 1>", "subject_definitions:", "retention_analysis:", "detailed_description:", "overall_soundscape:", "non_diegetic_music:", "TAKE LENGTH", "ONE continuous [Shot 1]"):
        assert needed in writer, needed
    # Filmed take prompts and editorial JSON agree without asking H3 to bake in the cuts.
    planner = (folder / "timeline_planner.txt").read_text(encoding="utf-8")
    example = json.loads((folder.parent / "timeline_fashion_motion.json").read_text(encoding="utf-8"))
    assert 'editorial instructions in JSON' in planner
    for shot in example["shots"]:
        text = (shot["prompt"] + shot["image_prompt"]).lower()
        assert 'one continuous filmed take' in text, shot['id']
        if shot.get("sub_cuts"):
            assert 'editorial crops and transitions are applied separately' in text, shot['id']
    assert len(writer.split()) < 2100  # a prompt a local model can follow: 1793 words without the dialogue and plate modules, which are off unless a voice, a dialogue or a place is given


def test_negations_are_removed_from_prompts_but_cuts_and_transitions_stay():
    from majoor_videotools.core.prompt_guard import clean_plan_text, strip_negations

    text, gone = strip_negations("The person from <Picture 1> stands on a white floor. Locked-off camera, no cuts, soft light. One continuous take, no cuts, no text.")
    assert text == "The person from <Picture 1> stands on a white floor. Locked-off camera, soft light." and len(gone) == 4
    kept = "A fast hook: 0.0-0.5 s wide frame; 0.5-1.0 s close-up, the last cut whipping into the next shot. A low-cut dress with a textured collar."
    assert strip_negations(kept) == (kept, [])  # cuts, whip and framing are described on purpose
    assert strip_negations("Slow push-in, without subtitles or logos in a single continuous shot.")[0] == "Slow push-in."
    sections = "overall_soundscape:\nQuiet room tone.\n\n[Shot 1 (0.0-0.4 s)] Wide frame, no text.\nnon_diegetic_music:\nNone."
    assert strip_negations(sections)[0] == "overall_soundscape:\nQuiet room tone.\n\n[Shot 1 (0.0-0.4 s)] Wide frame.\nnon_diegetic_music:\nNone."
    plan = json.dumps({"shots": [{"duration": 1, "prompt": "A woman walks. One continuous take, no cuts, no text.", "image_prompt": "Portrait, white studio, no text.", "notes": "no cuts here"}]})
    cleaned, gone = clean_plan_text(plan)
    shot = json.loads(cleaned)["shots"][0]
    assert shot == json.loads(plan)["shots"][0] and gone == []
    assert clean_plan_text("not json")[0] == "not json"


def test_card_text_is_never_cut_off():
    from PIL import Image

    from majoor_videotools.core.card_text import MIN_SIZE, LINE, draw_card_text, layout, wrap, font

    words = [f"word{i}" for i in range(600)]  # a very long prompt
    prompt = " ".join(words)
    for width, height in ((432, 768), (180, 320), (768, 432), (96, 96)):
        blocks = [("SHOT_001 · 1.00s", 1.5, True), ("role: hook\ntransition in: flash (4 frames)\ncuts (3): 0.50s / 0.25s / 0.25s", 1.0, False), ("PROMPT", 0.9, True), (prompt, 1.0, False)]
        size, placed = layout(blocks, width - 10, height - 10, 40)
        used = sum(len(lines) * px * LINE for lines, px, _ in placed)
        assert used <= height - 10 + 1e-6 or size == MIN_SIZE, (width, height, size)
        flat = " ".join(" ".join(lines) for lines, _, _ in placed).split()
        assert [w for w in flat if w.startswith("word")] == words  # every word is there, in order
        for lines, px, bold in placed:
            assert all(font(px, bold).getlength(line) <= width - 10 + 1 for line in lines)  # and nothing is wider than the card
    long_word = "x" * 300
    lines = wrap(f"a {long_word} b", font(14), 200)
    assert "".join(lines).replace(" ", "").count("x") == 300 and lines[0] == "a" or "".join(lines).count("x") == 300  # a word longer than the card is broken, not dropped
    card = Image.new("RGB", (432, 768), (30, 30, 60))
    draw_card_text(card, [("SHOT_001", 1.5, True), ("a short brief", 1.0, False)])
    assert card.getextrema() != ((30, 30), (30, 30), (60, 60))  # something was written
    assert card.getchannel(0).getextrema()[1] > 200  # in white on a dark card


def test_cards_show_the_brief_of_the_shot_unless_turned_off(root, tmp_path):
    from PIL import Image

    plan = json.dumps({"fps": 24, "aspect_ratio": "9:16", "shots": [
        {"id": "HOOK", "duration": 1.0, "color": "#203040", "prompt": "The person from <Picture 1> stands full-body. " * 20, "notes": "Hook: full body then two punch-ins.", "transition": "flash",
         "sub_cuts": [{"duration": 0.5}, {"duration": 0.25, "zoom": 1.9}, {"duration": 0.25, "flip": True}]},
        {"id": "HOLD", "duration": 1.0, "color": "white", "prompt": "A calm hold."}]})
    with_text = template(root, plan=plan)
    without = template(root, plan=plan, card_text=False)
    assert with_text.project_id != without.project_id  # another card, another project
    store = ProjectStore(root, with_text.project_id)
    cards = {}
    for name in ("HOOK", "HOLD"):
        cards[name] = Image.open(store.resolve(f"cache/slates/{name}.png"))
        assert cards[name].size == (180, 320) or cards[name].size[1] >= 300
    plain = Image.open(ProjectStore(root, without.project_id).resolve("cache/slates/HOOK.png"))
    assert len(plain.getcolors(maxcolors=100)) == 1 and len(cards["HOOK"].getcolors(maxcolors=100000)) > 1  # plain card, written card
    assert cards["HOLD"].getchannel(0).getextrema()[0] < 60 and cards["HOLD"].getchannel(0).getextrema()[1] == 255  # dark letters on the white card
    cards["HOOK"].save(tmp_path / "card.png")


def _frame(path, at, tmp_path, name="f.png"):
    import subprocess

    from PIL import Image

    out = tmp_path / name
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(at), "-i", str(path), "-frames:v", "1", str(out)], check=True)
    return Image.open(out).convert("RGB")


def test_overlays_and_splits_are_read():
    plan = parse_plan(json.dumps({"shots": [
        {"id": "A", "duration": 2, "split": {"layout": "left_right", "panels": [{"source": "self", "flip": True}, {"source": "B", "zoom": 1.5}]},
         "overlay": [{"source": "B", "opacity": 0.4, "blend": "add"}, {"source": "self", "scale": 0.4, "position": "bottom_right"}], "refs": [2, 1, 2],
         "sub_cuts": [{"duration": 1, "split": None}, {"duration": 1, "split": "grid_4"}]},
        {"id": "B", "duration": 1}]}), 24, "16:9", 320)
    fx = plan.shots[0].fx
    assert fx["split"]["layout"] == "left_right" and [p["source"] for p in fx["split"]["panels"]] == ["self", "B"] and fx["split"]["panels"][0]["flip"] is True
    assert [(o["source"], o["blend"], o["opacity"], o["scale"], o["position"]) for o in fx["overlay"]] == [("B", "add", 0.4, 1.0, "center"), ("self", "screen", 0.5, 0.4, "bottom_right")]
    assert fx["refs"] == [1, 2] and fx["sub_cuts"][0]["split"] is None and fx["sub_cuts"][1]["split"]["layout"] == "grid_4" and len(fx["sub_cuts"][1]["split"]["panels"]) == 4
    for text, message in (
        ('{"shots": [{"duration": 1, "split": {"layout": "diagonal"}}]}', "unknown split layout"),
        ('{"shots": [{"duration": 1, "split": {"layout": "left_right", "panels": [{}, {}, {}]}}]}', "has 2 panels"),
        ('{"shots": [{"duration": 1, "overlay": [{"blend": "glow"}]}]}', "unknown blend"),
        ('{"shots": [{"duration": 1, "overlay": [{"source": "a b"}]}]}', "invalid source"),
        ('{"shots": [{"duration": 1, "overlay": [{}, {}, {}, {}]}]}', "at most 3 overlays"),
        ('{"shots": [{"duration": 1, "refs": [10]}]}', "refs must be between"),
    ):
        with pytest.raises(MajoorError, match=message):
            parse_plan(text, 24, "16:9", 320)


def test_split_screens_and_surimpressions_are_composed(root, fixtures, tmp_path):
    import numpy as np

    plan = json.dumps({"fps": 24, "aspect_ratio": "9:16", "shots": [
        {"id": "SPLIT", "duration": 1.0, "split": {"layout": "left_right", "panels": [{"source": "self"}, {"source": "self", "flip": True}]}, "transition": "flash"},
        {"id": "MIX", "duration": 1.0, "overlay": [{"source": "OTHER", "opacity": 0.5, "blend": "normal", "look": "negative"}], "sub_cuts": [{"duration": 0.5}, {"duration": 0.5, "split": "grid_4"}]},
        {"id": "PIP", "duration": 1.0, "overlay": [{"source": "self", "scale": 0.4, "position": "bottom_right", "opacity": 1}]},
        {"id": "OTHER", "duration": 1.0},
        {"id": "LOST", "duration": 1.0, "overlay": [{"source": "GHOST"}]}]})
    sl = template(root, plan=plan)
    assert any("GHOST" in w for w in sl.detection.warnings)  # a source the plan does not have is replaced and reported
    for sid in ("SPLIT", "MIX", "PIP", "OTHER"):  # LOST keeps its placeholder
        shot = sl.get_shot(sid)
        sl = apply_revision(sl, root, make_metadata(sl, shot, shot.active), fixtures["gen"])
    res = assemble_shots(sl, root, AssemblyOptions(audio_policy="mute", missing_shot_policy="use_original"))
    assert probe(res.path).frame_count == 120 and (probe(res.path).width, probe(res.path).height) == (sl.source.width, sl.source.height)
    graph = next((ProjectStore(root, sl.project_id).resolve("logs")).glob("filter_*.txt")).read_text(encoding="utf-8")
    assert "hstack=inputs=2" in graph and "xstack=inputs=4" in graph and "blend=all_mode=normal" in graph and "overlay=x=" in graph
    split = np.asarray(_frame(res.path, 0.5, tmp_path, "split.png"), dtype=float)
    w = split.shape[1] // 2
    left, right = split[:, :w], split[:, split.shape[1] - w:]
    assert np.abs(left - right[:, ::-1]).mean() < 8 and np.abs(left - right).mean() > 15  # the right panel is the mirror of the left one
    mix = np.asarray(_frame(res.path, 1.25, tmp_path, "mix.png"), dtype=float)  # a take half blended with its own negative: nearly gray
    assert mix.std(axis=(0, 1)).mean() < 60
    pip = _frame(res.path, 2.5, tmp_path, "pip.png")
    plain = np.asarray(_frame(res.path, 3.5, tmp_path, "plain.png"), dtype=float)
    assert pip.size == (sl.source.width, sl.source.height) and abs(plain.mean() - np.asarray(pip, dtype=float).mean()) < 120
    again = assemble_shots(sl, root, AssemblyOptions(audio_policy="mute", missing_shot_policy="use_original"))
    assert again.reused and again.path == res.path


def test_a_layer_from_a_shot_without_take_falls_back_to_the_shot(root, fixtures):
    plan = json.dumps({"fps": 24, "aspect_ratio": "9:16", "shots": [{"id": "HOST", "duration": 1.0, "split": {"layout": "top_bottom", "panels": [{"source": "self"}, {"source": "LATER"}]}}, {"id": "LATER", "duration": 1.0}]})
    sl = template(root, plan=plan)
    host = sl.get_shot("HOST")
    sl = apply_revision(sl, root, make_metadata(sl, host, host.active), fixtures["gen"])
    res = assemble_shots(sl, root, AssemblyOptions(audio_policy="mute", missing_shot_policy="use_original"))
    assert any("LATER has no generated take for the panel" in w for w in res.warnings) and probe(res.path).frame_count == 48


def test_the_dynamic_edit_skill_example_is_a_valid_plan_with_composed_shots(root):
    from pathlib import Path

    from majoor_videotools.core.fx import describe_shot

    base = Path(__file__).resolve().parents[2] / "examples"
    example = (base / "dynamic_edit_product_ad.json").read_text(encoding="utf-8")
    skill = (base / "prompts" / "dynamic_edit_skill.txt").read_text(encoding="utf-8")
    assert example.strip() in skill and "MODE B" in skill and "split" in skill and "surimpression" in skill
    plan = parse_plan(example, 24, "16:9", 320)
    assert len(plan.shots) == 6 and sum(s.frames for s in plan.shots) == 192 and plan.fps == 24
    ids = {s.shot_id for s in plan.shots}
    layers = [layer for s in plan.shots for layer in (s.fx.get("overlay") or [])] + [p for s in plan.shots for p in (s.fx.get("split") or {}).get("panels", [])]
    assert {l["source"] for l in layers} - {"self"} <= ids and len(layers) >= 4  # every source is a shot of the plan
    assert [s.shot_id for s in plan.shots if s.fx.get("split") or s.fx.get("overlay")] == ["SHOT_002", "SHOT_003", "SHOT_005"]  # three accents in 8 seconds
    assert all(s.fx.get("refs") for s in plan.shots) and plan.shots[2].fx["refs"] == [1, 2]
    for shot in plan.shots:
        text = (shot.prompt + shot.image_prompt).lower()
        assert "continuous" not in text and "no cuts" not in text and "no text" not in text and "<picture" in shot.prompt.lower(), shot.shot_id
        if shot.fx.get("sub_cuts"):
            assert sum(c["weight"] for c in shot.fx["sub_cuts"]) == shot.frames
            assert "[shot " not in shot.prompt.lower(), shot.shot_id
    sl = template(root, plan=example)
    assert not [w for w in sl.detection.warnings if "plan" in w]  # nothing refers to a shot that does not exist
    three = sl.get_shot("SHOT_003")
    _, words = describe_shot("SHOT_003", 2.0, 1.5, three.frame_count, three.plan, 24.0)
    assert "split left_right (self, SHOT_004)" in words and "pictures <Picture 1>, <Picture 2>" in words
    _, echo = describe_shot("SHOT_002", 1.0, 1.0, sl.get_shot("SHOT_002").frame_count, sl.get_shot("SHOT_002").plan, 24.0)
    assert "overlay self screen 0.35" in echo


def _level(path, start, length):
    """RMS of a part of the audio of a video."""
    import subprocess

    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(length), "-i", str(path), "-vn", "-f", "f32le", "-ac", "1", "-ar", "22050", "-"], capture_output=True, check=True).stdout
    return float(np.sqrt(np.mean(np.frombuffer(raw, np.float32) ** 2)))


def test_music_and_sfx_are_mixed_over_the_edit(root, tmp_path):
    sl = template(root)  # 6 s of placeholder cards
    sine = lambda hz, seconds, level: np.repeat((level * np.sin(2 * np.pi * hz * np.arange(int(22050 * seconds)) / 22050))[:, None], 2, axis=1).astype(np.float32)
    music, sfx = tmp_path / "music.wav", tmp_path / "sfx.wav"
    write_wav(music, sine(220, 10, 0.3), 22050)  # longer than the edit
    write_wav(sfx, sine(1000, 2, 0.6), 22050)  # shorter than the edit
    base = dict(missing_shot_policy="use_original", audio_policy="mute")
    silent = assemble_shots(sl, root, AssemblyOptions(**base))
    assert not probe(silent.path).has_audio
    with_music = assemble_shots(sl, root, AssemblyOptions(**base, music=music, music_fade=1.0))
    info = probe(with_music.path)
    assert info.has_audio and info.frame_count == 144 and with_music.path != silent.path
    assert _level(with_music.path, 2, 1) > 0.2 and _level(with_music.path, 5.5, 0.5) < _level(with_music.path, 2, 1) / 2  # fades out
    both = assemble_shots(sl, root, AssemblyOptions(**base, music=music, sfx=sfx, sfx_volume=1.0))
    assert both.path != with_music.path and _level(both.path, 0.5, 1) > _level(both.path, 3, 1) * 1.2  # the sfx track is there, then it ends
    assert assemble_shots(sl, root, AssemblyOptions(**base, music=music, sfx=sfx, sfx_volume=1.0)).reused


def test_music_mixes_with_the_source_audio(root, tmp_path):
    music = click_track(tmp_path / "m.wav", 120, 8)
    sl = template(root, audio_wav=music)
    loud = tmp_path / "loud.wav"
    write_wav(loud, np.repeat((0.4 * np.sin(2 * np.pi * 330 * np.arange(22050 * 8) / 22050))[:, None], 2, axis=1).astype(np.float32), 22050)
    plain = assemble_shots(sl, root, AssemblyOptions(missing_shot_policy="use_original"))
    mixed = assemble_shots(sl, root, AssemblyOptions(missing_shot_policy="use_original", music=loud, music_volume=0.5))
    assert probe(mixed.path).has_audio and _level(mixed.path, 1, 1) > _level(plain.path, 1, 1)


def test_detected_shots_become_a_rhythm_skeleton():
    from types import SimpleNamespace as NS

    from majoor_videotools.core.timeline_sources import plan_from_shots, plan_text, rhythm_text

    cuts = [(0, 48), (48, 51), (51, 54), (54, 120)]
    shot_list = NS(source=NS(fps_num=24, fps_den=1, width=1080, height=1920, rotation=0), shots=[NS(start_frame=a, end_frame_exclusive=b) for a, b in cuts])
    plan = plan_from_shots(shot_list)
    assert plan["aspect_ratio"] == "9:16" and plan["fps"] == 24
    assert [r["duration_frames"] for r in plan["shots"]] == [48, 6, 66]
    assert plan["shots"][1]["sub_cuts"] == [{"duration_frames": 3}, {"duration_frames": 3}]
    text = plan_text(plan)
    assert len(parse_plan(text, 24, "16:9", 64).shots) == 3 and rhythm_text(text, 24).startswith("EDIT RHYTHM: 3 shots, 4 cuts, 5.00 s")


def test_transition_names_of_an_llm_are_understood_and_every_filter_renders(tmp_path):
    import subprocess
    from fractions import Fraction

    from majoor_videotools.core.fx import TRANSITIONS, parse_fx, transition_filters

    plan = parse_plan(json.dumps({"shots": [{"duration": 1, "transition": "flash_white"}, {"duration": 1, "transition": "Cross Dissolve"}, {"duration": 1, "transition": "swirl"}, {"duration": 1, "transition": {"type": "rgb_split", "frames": 5}}]}), 24, "16:9", 320)
    assert [(s.fx.get("transition") or {}).get("type") for s in plan.shots] == ["flash", "blur", None, "glitch"] and plan.shots[3].fx["transition"]["frames"] == 5
    clip = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=160x120:r=24:d=1", "-pix_fmt", "yuv420p", str(clip)], check=True)
    for kind, frames in TRANSITIONS.items():
        chain = ",".join(transition_filters({"type": kind, "frames": frames} if kind != "cut" else None, 24, Fraction(24), 160, 120, include_punch=True)) or "null"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-vf", chain, "-frames:v", "24", str(tmp_path / f"{kind}.mp4")], check=True)


def test_a_color_that_is_not_one_does_not_stop_the_plan():
    plan = parse_plan('{"shots": [{"duration": 1, "color": "none", "text": {"content": "hi", "color": "transparent", "background": "none"}}, {"duration": 1, "color": "navy"}]}', 24, "16:9", 320)
    assert plan.shots[0].color == "" and plan.shots[1].color == "navy"
    text = plan.shots[0].fx["text"]
    assert text["color"] == "white" and "background" not in text


def test_an_aspect_ratio_that_the_engine_does_not_have_gives_the_one_of_the_node():
    assert parse_plan('{"aspect_ratio": "2.39:1", "shots": [{"duration": 1}]}', 24, "9:16", 320).height > parse_plan('{"aspect_ratio": "2.39:1", "shots": [{"duration": 1}]}', 24, "9:16", 320).width
    with pytest.raises(MajoorError, match="not supported"):
        parse_plan('{"aspect_ratio": "2.39:1", "shots": [{"duration": 1}]}', 24, "21:9", 320)


def test_the_location_of_a_shot_goes_through_the_plan():
    from majoor_videotools.core.timeline_sources import merge_plans, plan_to_dict
    from majoor_videotools.core.prompt_guard import clean_plan_text

    place = "A zinc rooftop terrace in Paris at dusk, string lights, no people around"
    plan = parse_plan(json.dumps({"shots": [{"id": "A", "duration": 1, "prompt": "x", "location": place}, {"id": "B", "duration": 1, "prompt": "y"}]}), 24, "9:16", 256)
    assert [s.location for s in plan.shots] == [place, ""]
    rows = plan_to_dict(plan)["shots"]
    assert rows[0]["location"] == place and "location" not in rows[1]
    merged, _ = merge_plans(json.dumps({"shots": [{"id": "A", "duration": 1}, {"id": "B", "duration": 1}]}), json.dumps({"shots": [{"id": "A", "prompt": "x", "location": place}, {"id": "B", "prompt": "y", "location": place}]}), 24, "9:16", 256)
    assert [r["location"] for r in merged["shots"]] == [place, place]
    cleaned = json.loads(clean_plan_text(json.dumps({"shots": [{"id": "A", "location": "A quiet street, no text, shops open"}]}))[0])
    assert "no text" in cleaned["shots"][0]["location"] and "shops open" in cleaned["shots"][0]["location"]


def test_a_plan_is_fitted_to_the_length_that_was_asked_for():
    import json

    from majoor_videotools.core.timeline_sources import fit_duration

    plan = {"shots": [{"duration": 3.08, "prompt": "a", "sub_cuts": [{"duration": 1.5}, {"duration": 1.58}]}, {"duration": "2.5", "prompt": "b"}, {"sub_cuts": [{"duration": "1s"}, {"duration": 1}], "prompt": "c"}]}
    fitted = json.loads(fit_duration(json.dumps(plan), 20, 24))
    assert sum(int(s["duration"][:-1]) for s in fitted["shots"]) == 480
    assert sum(int(c["duration"][:-1]) for c in fitted["shots"][0]["sub_cuts"]) in (194, 195, 196)
    assert fit_duration("not json", 20, 24) == "not json"


def test_a_music_plan_groups_grid_steps_into_takes_with_sub_cuts(tmp_path):
    import numpy as np

    from majoor_videotools.core.timeline_sources import plan_from_music

    rate, period = 22050, 60 / 140
    samples = np.zeros(rate * 15, dtype=np.float32)
    for k in range(int(15 / period)):
        samples[int(k * period * rate):int(k * period * rate) + 300] = np.hanning(300)
    steps, _ = plan_from_music(samples, rate, cut_every="2_beats", fps=24)
    takes, _ = plan_from_music(samples, rate, cut_every="2_beats", shots=5, fps=24)
    assert len(steps["shots"]) == 18 and len(takes["shots"]) == 5
    assert sum(s["duration_frames"] for s in takes["shots"]) == sum(s["duration_frames"] for s in steps["shots"])
    assert all(sum(c["duration_frames"] for c in s["sub_cuts"]) == s["duration_frames"] for s in takes["shots"])
    assert sum(len(s["sub_cuts"]) for s in takes["shots"]) == 18


def test_the_sound_of_a_take_follows_the_speed_of_its_cut():
    from majoor_videotools.core.assembler import atempo_filters

    assert atempo_filters(1.0) == "" and atempo_filters(2.0) == ",atempo=2.000000"
    assert atempo_filters(3.0) == ",atempo=2.0,atempo=1.500000" and atempo_filters(0.3) == ",atempo=0.5,atempo=0.600000"
