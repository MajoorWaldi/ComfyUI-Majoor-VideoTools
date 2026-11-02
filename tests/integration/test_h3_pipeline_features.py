"""Lip sync measurement, word-based phrase cuts, character references, the Creative Director and the stage runner."""
import json

import numpy as np
import pytest

from majoor_videotools.core import casting as casting_mod
from majoor_videotools.core.creative_director import choose_sizes
from majoor_videotools.core.errors import MajoorError
from majoor_videotools.core.lipsync import (control_region, lagged_correlation, lipsync_report, measure_video, mouth_opening, needs_retake,
                                            next_seed, speech_envelope)
from majoor_videotools.core.music_cuts import music_cut_plan

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


def test_speech_envelope_and_mouth_opening_read_the_signals():
    rate = 8000
    samples = np.concatenate([np.zeros(rate), np.sin(np.linspace(0, 2000, rate)) * .5])
    env = speech_envelope(samples, rate, 24.0, 48)
    assert env[:20].max() == 0 and env[30:].min() > .5 and env.max() == 1
    assert speech_envelope(np.zeros(rate), rate, 24.0, 24).max() == 0
    flat, striped = np.zeros((4, 4)), np.tile([0.0, 8.0], (4, 2))
    opening = mouth_opening([flat, striped, None, flat])
    assert opening[0] == 0 and opening[1] == 4 and np.isnan(opening[2]) and opening[3] == 0  # a frame without a face is not measured
    with pytest.raises(MajoorError):
        speech_envelope(np.array([np.nan]), rate, 24.0, 3)


def test_what_the_rest_of_the_face_does_is_taken_away_from_the_mouth():
    voice = speaking()
    head = voice * 6 + 1  # the whole face changes with the voice: a head that bobs
    stripes = np.tile([0.0, 8.0], (4, 2))
    crops = [stripes * level for level in head]
    controls = [stripes * level for level in head]
    with_control = mouth_opening(crops, controls)
    assert np.nanmax(np.abs(with_control)) < 1e-9
    assert lipsync_report(with_control + np.random.default_rng(4).normal(0, .01, len(voice)), voice, FPS)["status"] == "fail"
    own = mouth_opening([stripes * level for level in voice * 6 + 1], [stripes * 3 for _ in voice])
    assert lipsync_report(own, voice, FPS)["status"] == "pass"


def test_the_control_region_is_above_the_mouth_or_below_it_or_missing():
    assert control_region((.3, .55, .4, .2)) == pytest.approx((.3, .05, .4, .2))
    assert control_region((.3, .1, .4, .2)) == pytest.approx((.3, .6, .4, .2))
    assert control_region((.3, .3, .4, .4)) is None


def test_the_score_must_beat_what_chance_gives_on_this_voice():
    voice = speaking()
    report = lipsync_report(voice * 5 + .1, voice, FPS)
    assert report["status"] == "pass" and report["chance"] < report["score"]
    assert lipsync_report(voice[:25] * 5, voice[:25], FPS)["chance"] == 0.0  # too short to move the voice away from itself


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
