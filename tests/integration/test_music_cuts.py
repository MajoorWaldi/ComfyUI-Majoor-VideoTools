import json
import subprocess

import numpy as np
import pytest

from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.music_cuts import apply_music_timing, music_cut_plan
from majoor_videotools.core.template import parse_plan
from majoor_videotools.core.timeline_sources import plan_from_music


def audio(seconds=24, rate=8000):
    t = np.arange(round(seconds * rate)) / rate
    wave = .03 * np.sin(2 * np.pi * 220 * t)
    for at in np.arange(.5, seconds, .5):
        i = round(at * rate)
        n = min(round(.05 * rate), len(wave) - i)
        wave[i:i + n] += .5 * np.sin(2 * np.pi * 80 * t[:n]) * np.exp(-t[:n] * 60)
    return wave, rate


def lengths(plan):
    return [s["duration_frames"] for s in plan["shots"]]


@pytest.mark.parametrize("mode", ["adaptive", "random", "regular"])
def test_exact_frame_coverage_and_no_tiny_segments(mode):
    samples, rate = audio()
    plan, _ = music_cut_plan(samples, rate, duration=23.731, mode=mode)
    assert sum(lengths(plan)) == round(23.731 * 24)
    assert min(lengths(plan)) >= 5


@pytest.mark.parametrize("mode", ["adaptive", "random"])
def test_musical_phrases_mix_holds_beats_and_halfbeat_bursts(monkeypatch, mode):
    from majoor_videotools.core import audio_events, music_cuts
    monkeypatch.setattr(music_cuts, "detect_beats", lambda *args: (144, np.arange(0, 24, 60 / 144)))
    monkeypatch.setattr(audio_events, "band_hits", lambda *args: {"kick": [], "snare": [], "hihat": []})
    samples = np.ones(8000 * 24)
    plan, _ = music_cut_plan(samples, 8000, duration=24, mode=mode)
    frames = lengths(plan)
    assert sum(frames) == 576
    assert min(frames) >= 5
    assert any(a == b == 5 for a, b in zip(frames, frames[1:]))
    assert 10 in frames and 20 in frames
    assert max(frames) >= 40
    assert plan == music_cut_plan(samples, 8000, duration=24, mode=mode)[0]
    merged, _ = apply_music_timing('{"shots":[{"id":"take","duration":24,"prompt":"City"}]}',
                                 plan, 24, "16:9", 64)
    parsed = parse_plan(json.dumps(merged), 24, "16:9", 64)
    assert len(parsed.shots) == 1
    assert [c["weight"] for c in parsed.shots[0].fx["sub_cuts"]] == frames


def test_regular_halfbeats_at_144_bpm_are_not_dropped(monkeypatch):
    from majoor_videotools.core import timeline_sources
    monkeypatch.setattr(timeline_sources, "detect_beats", lambda *args: (144, np.arange(0, 10, 60 / 144)))
    plan, _ = music_cut_plan(np.ones(80000), 8000, duration=10, mode="regular", cut_every="half_beat")
    assert lengths(plan) == [5] * 48


def test_five_frame_edit_keeps_minimax_generation_contract():
    from majoor_videotools.core.template import generation_frames
    plan = parse_plan('{"shots":[{"duration_frames":5}]}', 24, "16:9", 64)
    assert plan.shots[0].frames == 5
    assert generation_frames(5, "minimax_h3") == 124


def test_seed_reproducibility_and_variation():
    samples, rate = audio()
    make = lambda seed, variation: music_cut_plan(samples, rate, duration=24, mode="random", seed=seed, variation=variation, sync=0)[0]
    assert make(12, .8) == make(12, .8)
    assert make(12, .8) != make(13, .8)
    assert len(set(lengths(make(12, 0))) - {lengths(make(12, 0))[-1]}) <= 1
    assert len(set(lengths(make(12, .8)))) > 2


def test_density_controls_actual_cuts_without_new_generations():
    samples, rate = audio()
    plans = [music_cut_plan(samples, rate, duration=24, mode="random", density=d, variation=0)[0]
             for d in ("low", "medium", "high")]
    assert len(plans[0]["shots"]) < len(plans[1]["shots"]) < len(plans[2]["shots"])
    text = json.dumps({"shots": [{"id": "red", "duration": 12, "prompt": "Red"}, {"id": "blue", "duration": 12, "prompt": "Blue"}]})
    for timing in plans:
        merged, _ = apply_music_timing(text, timing, 24, "16:9", 64)
        parsed = parse_plan(json.dumps(merged), 24, "16:9", 64)
        assert [s.shot_id for s in parsed.shots] == ["red", "blue"]
        assert [s.prompt for s in parsed.shots] == ["Red", "Blue"]
        assert sum(s.frames for s in parsed.shots) == 576
        cuts = [c["weight"] for s in parsed.shots for c in s.fx.get("sub_cuts", [{"weight": s.frames}])]
        assert cuts == lengths(timing)


def test_acoustic_energy_changes_pacing_and_selected_mood_biases_holds():
    samples, rate = audio(32)
    samples[:16 * rate] *= .03
    plan, _ = music_cut_plan(samples, rate, duration=32, variation=0, sync=0)
    ends = np.cumsum(lengths(plan))
    quiet = [n for n, end in zip(lengths(plan), ends) if end < 16 * 24]
    energetic = [n for n, end in zip(lengths(plan), ends) if end - n >= 16 * 24]
    assert np.mean(quiet) > 1.3 * np.mean(energetic)
    calm, _ = music_cut_plan(samples, rate, duration=32, variation=0, sync=0, mood="calm")
    intense, _ = music_cut_plan(samples, rate, duration=32, variation=0, sync=0, mood="intense")
    assert len(calm["shots"]) < len(intense["shots"])


def test_sync_moves_boundaries_to_actual_accents(monkeypatch):
    from majoor_videotools.core import audio_events, music_cuts
    monkeypatch.setattr(music_cuts, "detect_beats", lambda *args: (0, []))
    monkeypatch.setattr(audio_events, "band_hits", lambda *args: {"kick": [(n * 2 + .3, 1) for n in range(12)], "snare": [], "hihat": []})
    samples, rate = audio()
    aligned, _ = music_cut_plan(samples, rate, duration=24, mode="random", sync=1, variation=0)
    loose, _ = music_cut_plan(samples, rate, duration=24, mode="random", sync=0, variation=0)
    assert aligned != loose
    accent_frames = {round((n * 2 + .3) * 24) for n in range(12)}
    assert set(np.cumsum(lengths(aligned))[:-1]).issubset(accent_frames)


def test_silence_uses_documented_narrative_fallback():
    plan, info = music_cut_plan(np.zeros(8000 * 20), 8000, duration=20, seed=3)
    assert info["timing_source"] == "narrative"
    assert info["bpm"] is None
    assert info["warnings"]
    assert sum(lengths(plan)) == 480
    assert len(plan["shots"]) > 1


def test_regular_preserves_the_existing_grid():
    samples, rate = audio()
    assert music_cut_plan(samples, rate, duration=24, mode="regular", cut_every="bar") == plan_from_music(samples, rate, duration=24, cut_every="bar")


def test_more_requested_takes_are_not_silently_discarded():
    text = json.dumps({"shots": [{"id": str(i + 1), "duration": 1, "prompt": str(i)} for i in range(5)]})
    timing = {"fps": 24, "shots": [{"duration_frames": 240}]}
    merged, notes = apply_music_timing(text, timing, 24, "16:9", 64)
    assert len(merged["shots"]) == 5
    assert sum(row["duration_frames"] for row in merged["shots"]) == 240
    assert notes and "extra take boundaries" in notes[0]


def test_continuous_action_is_not_broken_into_musical_repeats():
    text = json.dumps({"shots": [{"duration": 8, "prompt": "One continuous camera move", "story": {"protect_action": True}}]})
    timing = {"fps": 24, "shots": [{"duration_frames": 48} for _ in range(4)]}
    merged, notes = apply_music_timing(text, timing, 24, "16:9", 64)
    assert merged["shots"][0]["duration_frames"] == 192
    assert "sub_cuts" not in merged["shots"][0]
    assert any("continuous action preserved" in n for n in notes)


def test_reference_beats_are_retained_without_resnapping_selected_cuts(tmp_path):
    from majoor_videotools.core.template import create_template
    sl = create_template(json.dumps({"shots": [{"duration_frames": 37}, {"duration_frames": 59}]}),
                         tmp_path, fps=24, aspect_ratio="1:1", resolution=64, profile="none",
                         thumbnails=False, card_text=False, reference_beats=(.5, 1., 1.5),
                         timing_warnings=("Narrative fallback warning",))
    assert [s.frame_count for s in sl.shots] == [37, 59]
    assert sl.detection.beat_times == (.5, 1., 1.5)
    assert "Narrative fallback warning" in sl.detection.warnings


def test_remix_excerpt_cuts_preserve_raw_takes_manifest_and_reference_boundaries(tmp_path):
    from dataclasses import replace
    from majoor_videotools.core.music_cuts import musical_take_cuts
    from majoor_videotools.core.revisions import apply_revision, make_metadata
    from majoor_videotools.core.template import create_template

    text = json.dumps({"shots": [{"id": "red", "duration": 8, "prompt": "Portrait"}]})
    sl = create_template(text, tmp_path, fps=24, aspect_ratio="1:1", resolution=64, profile="none", thumbnails=False, card_text=False)
    original = sl
    source = tmp_path / sl.project_id / sl.source.uri
    shot = sl.shots[0]
    sl = apply_revision(sl, tmp_path, make_metadata(sl, shot, shot.active), source)
    manifest = tmp_path / sl.project_id / "manifest.json"
    before = manifest.read_bytes()
    samples, rate = audio(8)
    edited = musical_take_cuts(sl, samples, rate, mode="adaptive", density="high", variation=0)
    assert edited.shots[0].revisions == sl.shots[0].revisions
    assert edited.shots[0].start_frame == sl.shots[0].start_frame
    assert edited.shots[0].end_frame_exclusive == sl.shots[0].end_frame_exclusive
    assert len(edited.shots[0].plan["fx"]["sub_cuts"]) > 1
    assert sum(c["frames"] for c in edited.shots[0].plan["fx"]["sub_cuts"]) == 192
    assert manifest.read_bytes() == before
    assert "sub_cuts" not in sl.shots[0].plan.get("fx", {})
    assert musical_take_cuts(sl, samples, rate, mode="free") is sl
    retained = musical_take_cuts(original, samples, rate, mode="adaptive")
    assert retained.shots == original.shots
    protected = replace(sl, shots=(replace(sl.shots[0], plan={**sl.shots[0].plan, "story": {"protect_action": True}}),))
    assert musical_take_cuts(protected, samples, rate, mode="adaptive").shots == protected.shots


def test_real_export_has_a_visible_jump_cut_without_invented_visual_effects(tmp_path):
    from majoor_videotools.core.assembler import AssemblyOptions, assemble_shots
    from majoor_videotools.core.media_probe import probe
    from majoor_videotools.core.revisions import apply_revision, make_metadata
    from majoor_videotools.core.template import create_template

    text = json.dumps({"shots": [{"id": "test", "duration": 2, "prompt": "Changing colors"}]})
    timing = {"fps": 24, "shots": [{"duration_frames": 36}, {"duration_frames": 5}, {"duration_frames": 7}]}
    merged, _ = apply_music_timing(text, timing, 24, "1:1", 64)
    assert merged["shots"][0]["sub_cuts"][1]["start"] == 0
    sl = create_template(json.dumps(merged), tmp_path, fps=24, aspect_ratio="1:1", resolution=64, profile="none", thumbnails=False, card_text=False)
    assert [c["frames"] for c in sl.shots[0].plan["fx"]["sub_cuts"]] == [36, 5, 7]
    source = tmp_path / "take.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:s=64x64:r=24:d=1",
                    "-f", "lavfi", "-i", "color=blue:s=64x64:r=24:d=1", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)], check=True)
    shot = sl.shots[0]
    sl = apply_revision(sl, tmp_path, make_metadata(sl, shot, shot.active), source)
    options = AssemblyOptions(audio_policy="mute", effects=True, sub_cuts=True)
    result = assemble_shots(sl, tmp_path, options)
    assert probe(result.path).frame_count == 48
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(result.path), "-vf", r"select=eq(n\,35)+eq(n\,36)",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(2, 64, 64, 3).mean(axis=(1, 2))
    assert frames[0, 2] > 200 and frames[1, 0] > 200
    assert assemble_shots(sl, tmp_path, options).reused


@pytest.mark.parametrize("changes", [{"variation": -1}, {"sync": 2}, {"mode": "bad"}, {"duration": 0}])
def test_invalid_options_are_explicit_errors(changes):
    with pytest.raises(MajoorError):
        music_cut_plan(np.zeros(8000), 8000, **({"duration": 1} | changes))
