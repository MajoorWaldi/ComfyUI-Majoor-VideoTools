"""Lip sync measurement, word-based phrase cuts, character references, the Creative Director and the stage runner."""
import json

import numpy as np
import pytest

from majoor_videotools.core import casting as casting_mod
from majoor_videotools.core.creative_director import choose_sizes
from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.lipsync import (lagged_correlation, lipsync_report, measure_video, mouth_motion, needs_retake, next_seed,
                                            speech_envelope)
from majoor_videotools.core.music_cuts import music_cut_plan
from majoor_videotools.core.orchestration import Cancelled, StageFailed, build_stages, retake_loop, run_pipeline

FPS = 24.0


def speaking(frames=96, seed=3):
    rng = np.random.default_rng(seed)
    envelope = np.clip(np.convolve(rng.random(frames), np.ones(4) / 4, "same") * 2 - .3, 0, 1)
    envelope[::17] = 1
    return envelope


# ---- lip sync ----------------------------------------------------------------------------------------------------------

def test_a_mouth_that_follows_the_voice_passes_and_the_delay_is_reported():
    voice = speaking()
    mouth = np.concatenate([np.zeros(3), voice[:-3]]) * 9 + .2  # three frames late
    report = lipsync_report(mouth, voice, FPS)
    assert report["status"] == "pass" and report["score"] > .9
    assert report["lag_ms"] == round(3 / FPS * 1000)


def test_an_unrelated_or_still_mouth_fails():
    voice = speaking()
    unrelated = np.random.default_rng(99).random(len(voice))
    assert lipsync_report(unrelated, voice, FPS)["status"] == "fail"
    still = lipsync_report(np.full(len(voice), 2.0), voice, FPS)
    assert still["status"] == "fail" and "does not move" in still["reason"]


def test_what_cannot_be_measured_is_never_a_verdict():
    voice = speaking()
    assert lipsync_report(np.full(len(voice), np.nan), voice, FPS)["status"] == "unmeasured"       # no face
    assert lipsync_report(voice, np.zeros(len(voice)), FPS)["status"] == "unmeasured"               # no voice
    assert lipsync_report(voice[:10], voice[:10], FPS)["status"] == "unmeasured"                    # too short
    assert lipsync_report(voice, np.full(len(voice), .8), FPS)["status"] == "unmeasured"            # a voice that never varies


def test_frames_without_a_face_are_left_out_of_the_comparison():
    voice = speaking()
    mouth = voice * 5 + .1
    mouth[10:25] = np.nan
    assert lipsync_report(mouth, voice, FPS)["status"] == "pass"


def test_speech_envelope_and_mouth_motion_read_the_signals():
    rate = 8000
    samples = np.concatenate([np.zeros(rate), np.sin(np.linspace(0, 2000, rate)) * .5])
    env = speech_envelope(samples, rate, 24.0, 48)
    assert env[:20].max() == 0 and env[30:].min() > .5 and env.max() == 1
    assert speech_envelope(np.zeros(rate), rate, 24.0, 24).max() == 0
    still = np.zeros((4, 4))
    moving = mouth_motion([still, still, still + 8, None, still])
    assert np.isnan(moving[0]) and moving[1] == 0 and moving[2] == 8 and np.isnan(moving[3]) and np.isnan(moving[4])  # no earlier frame: not measured
    with pytest.raises(MajoorError):
        speech_envelope(np.array([np.nan]), rate, 24.0, 3)


def test_lagged_correlation_sign_means_the_mouth_follows_the_voice():
    voice = speaking()
    late = np.concatenate([np.zeros(2), voice[:-2]])
    score, lag = lagged_correlation(late, voice, 6)
    assert lag == 2 and score > .99
    early = np.concatenate([voice[2:], np.zeros(2)])
    assert lagged_correlation(early, voice, 6)[1] == -2


def test_retake_policy_and_seeds():
    failed, passed, unmeasured = ({"status": s} for s in ("fail", "pass", "unmeasured"))
    assert needs_retake(failed, 1, 3) and needs_retake(failed, 2, 3) and not needs_retake(failed, 3, 3)
    assert not needs_retake(passed, 1, 3) and not needs_retake(unmeasured, 1, 3)
    assert next_seed(42, 1) != next_seed(42, 2) and next_seed(42, 1) == next_seed(42, 1)
    assert 0 <= next_seed(2 ** 31 - 1, 5) < 2 ** 31


def test_a_video_without_a_face_is_unmeasured(tmp_path):
    import subprocess
    path = tmp_path / "plain.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=320x240:d=2:r=24", "-f", "lavfi",
                    "-i", "sine=frequency=300:duration=2", "-shortest", "-pix_fmt", "yuv420p", str(path)], check=True)
    report = measure_video(path)
    assert report["status"] == "unmeasured" and ("face" in report["reason"] or "region" in report["reason"])
    fixed = measure_video(path, region=(.3, .5, .4, .3))  # a fixed region needs no detector; a flat grey picture has no mouth movement
    assert fixed["status"] == "fail" and "does not move" in fixed["reason"]


def test_the_mouth_region_is_checked():
    from majoor_videotools.core.lipsync import parse_region
    assert parse_region("") is None and parse_region("0.1,0.5,0.3,0.2") == (.1, .5, .3, .2)
    for bad in ("1,2,3", "a,b,c,d", "0.8,0.5,0.5,0.2", "0,0,0,0.1", "nan,0,1,1"):
        with pytest.raises(MajoorError):
            parse_region(bad)


# ---- retake loop -------------------------------------------------------------------------------------------------------

def test_retake_loop_keeps_the_first_good_take_and_the_best_of_all_bad_ones():
    made = []
    def generate(seed):
        made.append(seed)
        return f"take-{seed}"
    ok_after_two = iter([{"status": "fail", "score": .1}, {"status": "pass", "score": .8}])
    take, report, history = retake_loop(generate, lambda t: next(ok_after_two), 42)
    assert report["status"] == "pass" and len(history) == 2 and len(set(made)) == 2 and take == f"take-{made[1]}"
    scores = iter([.2, .4, .1])
    take, report, history = retake_loop(generate, lambda t: {"status": "fail", "score": next(scores)}, 7, max_attempts=3)
    assert len(history) == 3 and report["score"] == .4
    take, report, history = retake_loop(generate, lambda t: {"status": "unmeasured", "score": None}, 7)
    assert len(history) == 1
    with pytest.raises(MajoorError):
        retake_loop(generate, lambda t: {}, 1, max_attempts=0)


# ---- phrases from words ------------------------------------------------------------------------------------------------

def test_phrase_cuts_follow_the_words_when_they_are_given():
    rate = 8000
    samples = np.random.default_rng(1).normal(0, .1, rate * 12)
    words = [{"word": w, "start": a, "end": b} for w, a, b in
             [("one", 0.5, 1.0), ("two", 1.1, 1.8), ("three", 4.0, 4.6), ("four", 4.7, 5.5), ("five", 8.0, 9.0)]]
    plan, info = music_cut_plan(samples, rate, duration=12, fps=FPS, mode="phrases", words=json.dumps(words))
    assert info["timing_source"] == "word_phrases"
    cuts = np.cumsum([s["duration_frames"] for s in plan["shots"]])[:-1] / FPS
    assert len(cuts) == 2 and 1.8 < cuts[0] < 4.0 and 5.5 < cuts[1] < 8.0
    with pytest.raises(MajoorError):
        music_cut_plan(samples, rate, duration=12, fps=FPS, mode="phrases", words="{nope")


# ---- casting: references, sheets, auto sizes ----------------------------------------------------------------------------

CASTING = json.dumps({"style": "neon", "shot_sizes": "auto", "characters": [
    {"id": "ghoul", "name": "Ghoul", "look": "grey ghoul", "start": 0, "end": 6}, {"id": "witch", "name": "Witch", "look": "green witch", "start": 6, "end": 12}]})


def test_references_are_tied_to_known_characters_and_never_paths():
    cast = casting_mod.parse_casting(CASTING)
    assert casting_mod.parse_references('{"ghoul": "g.png", "witch": ["a.png", "b.png"]}', cast) == {"ghoul": ["g.png"], "witch": ["a.png", "b.png"]}
    assert casting_mod.parse_references("", cast) == {}
    for bad in ('{"nobody": "x.png"}', '{"ghoul": "../x.png"}', '{"ghoul": "/etc/x.png"}', '{"ghoul": []}', '{"ghoul": ["1","2","3","4","5","6"]}', "[1]", "{bad", '{"ghoul": 3}'):
        with pytest.raises(MajoorError):
            casting_mod.parse_references(bad, cast)


def test_the_character_sheet_prompt_carries_the_look_once():
    cast = casting_mod.parse_casting(CASTING)
    prompt = casting_mod.sheet_prompt(cast, "witch")
    assert "green witch" in prompt and "neon" in prompt and "neutral background" in prompt
    with pytest.raises(MajoorError):
        casting_mod.sheet_prompt(cast, "nobody")


def test_auto_is_accepted_and_other_values_fall_back():
    assert casting_mod.parse_casting(CASTING)["shot_sizes"] == "auto"
    odd = json.dumps({"shot_sizes": ["huge"], "characters": [{"id": "a", "name": "A", "look": "x", "start": 0, "end": 1}]})
    assert casting_mod.parse_casting(odd)["shot_sizes"] == ["medium", "close_up"]


def test_the_director_decides_from_duration_energy_and_place():
    rows = [{"id": "s1", "duration": 2.0}, {"id": "s2", "duration": .6}, {"id": "s3", "duration": .6, "energy": .9},
            {"id": "s4", "duration": 4.0, "energy": .1}, {"id": "s5", "duration": 2.0}]
    sizes = choose_sizes(rows, first_of_edit="s1")
    assert sizes["s1"] == "wide" and sizes["s2"] == "close_up" and sizes["s3"] == "extreme_close_up"
    assert sizes["s4"] == "wide" and sizes["s5"] == "medium"
    same = choose_sizes([{"id": str(i), "duration": .5} for i in range(6)])
    assert all(not (same[str(i)] == same[str(i + 1)] == same[str(i + 2)]) for i in range(4))
    assert choose_sizes([{"id": "only", "duration": 5.0}], first_of_edit="only") == {"only": "wide"}
    assert choose_sizes([]) == {}


# ---- stage runner ------------------------------------------------------------------------------------------------------

def test_stages_run_in_order_and_hand_results_forward():
    order = []
    def handler(name, value=None):
        def run(context):
            order.append(name)
            return value if value is not None else name
        return run
    stages = build_stages({name: handler(name) for name in ("plan", "casting", "shots", "assemble")})
    context, report = run_pipeline(stages, {"prompt": "go"})
    assert order == ["plan", "casting", "shots", "assemble"] and report.ok and context["shots"] == "shots" and context["prompt"] == "go"


def test_an_optional_failure_skips_only_what_needs_it():
    def boom(context):
        raise ValueError("no face model")
    handlers = {"plan": lambda c: 1, "shots": lambda c: 2, "casting": boom, "character_sheets": lambda c: 3, "lipsync": boom, "assemble": lambda c: 4}
    context, report = run_pipeline(build_stages(handlers))
    assert report.get("casting").status == "failed" and report.get("character_sheets").status == "skipped"
    assert report.get("lipsync").status == "failed" and report.get("assemble").status == "done" and "assemble" in context


def test_a_required_failure_stops_the_run_with_the_whole_report():
    handlers = {"plan": lambda c: 1, "shots": lambda c: (_ for _ in ()).throw(RuntimeError("gpu lost")), "assemble": lambda c: 4}
    with pytest.raises(StageFailed) as caught:
        run_pipeline(build_stages(handlers))
    assert caught.value.stage == "shots" and isinstance(caught.value.__cause__, RuntimeError)
    assert [s.status for s in caught.value.report.stages] == ["done", "failed", "skipped"]


def test_retries_cancellation_and_bad_wiring():
    calls = []
    def flaky(context):
        calls.append(1)
        if len(calls) < 3:
            raise OSError("busy")
        return "ok"
    context, report = run_pipeline(build_stages({"plan": lambda c: 1, "shots": flaky}, retries={"shots": 2}))
    assert report.get("shots").attempts == 3 and context["shots"] == "ok"
    with pytest.raises(Cancelled):
        run_pipeline(build_stages({"plan": lambda c: 1, "shots": lambda c: 2}), cancelled=lambda: True)
    with pytest.raises(MajoorError):
        build_stages({"plan": lambda c: 1})
    with pytest.raises(MajoorError):
        build_stages({"plan": lambda c: 1, "shots": lambda c: 1, "magic": lambda c: 1})
    from majoor_videotools.core.orchestration import Stage
    with pytest.raises(MajoorError):
        run_pipeline([Stage("b", lambda c: 1, needs=("a",)), Stage("a", lambda c: 1)])


def _talking_clip(tmp_path, follows: bool):
    """A synthetic take: a grey frame whose lower-middle region flickers as much as the voice is loud (or not at all)."""
    import subprocess
    import wave

    import cv2
    frames, rate = 72, 16000
    voice = speaking(frames, seed=5)
    rng = np.random.default_rng(0)
    silent_path = tmp_path / "silent.avi"
    writer = cv2.VideoWriter(str(silent_path), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (160, 120))
    for level in (voice if follows else np.full(frames, .5)):
        picture = np.full((120, 160), 100, np.uint8)
        picture[70:100, 50:110] = (100 + rng.integers(-1, 2, (30, 60)) * 90 * level).clip(0, 255).astype(np.uint8)
        writer.write(cv2.cvtColor(picture, cv2.COLOR_GRAY2BGR))
    writer.release()
    sound = np.concatenate([rng.normal(0, 1, rate // 24) * level for level in voice]) * 8000
    wav_path = tmp_path / "voice.wav"
    with wave.open(str(wav_path), "wb") as out:
        out.setnchannels(1), out.setsampwidth(2), out.setframerate(rate)
        out.writeframes(sound.clip(-32000, 32000).astype("<i2").tobytes())
    result = tmp_path / ("sync.mp4" if follows else "still.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(silent_path), "-i", str(wav_path), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "10", "-c:a", "aac", "-shortest", str(result)], check=True)
    return result


def test_a_real_file_is_measured_end_to_end_with_a_fixed_region(tmp_path):
    region = (.3, .55, .4, .3)
    good = measure_video(_talking_clip(tmp_path, True), region=region)
    assert good["status"] == "pass", good
    bad = measure_video(_talking_clip(tmp_path, False), region=region)
    assert bad["status"] == "fail", bad
