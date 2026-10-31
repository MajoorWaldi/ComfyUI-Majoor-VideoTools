import numpy as np

from majoor_videotools.core.music_cuts import music_cut_plan, vocal_phrases

RATE = 8000


def _track(spans, seconds=10):
    samples = np.zeros(seconds * RATE, dtype=np.float32)
    rng = np.random.default_rng(0)
    for a, b in spans:
        samples[int(a * RATE):int(b * RATE)] = rng.uniform(-.5, .5, int((b - a) * RATE))
    return samples


def test_phrases_are_split_at_pauses_and_short_noise_is_dropped():
    found = vocal_phrases(_track([(0.5, 3), (4, 6), (7, 7.2)]), RATE)
    assert [(round(x), round(y)) for x, y in found] == [(0, 3), (4, 6)] or [(round(x, 1), round(y, 1)) for x, y in found] == [(0.5, 3.0), (4.0, 6.0)]
    assert vocal_phrases(np.zeros(RATE, dtype=np.float32), RATE) == []


def test_phrases_mode_cuts_in_the_pauses():
    timing, info = music_cut_plan(_track([(0.5, 3), (4, 6), (7, 9.5)]), RATE, duration=10, fps=24, mode="phrases")
    lengths = [row["duration_frames"] for row in timing["shots"]]
    assert sum(lengths) == 240 and len(lengths) == 3
    assert lengths[0] == round(3.5 * 24) and lengths[1] == round(6.5 * 24) - round(3.5 * 24)
    assert info["timing_source"] == "vocal_phrases"


def test_phrases_mode_without_voice_is_one_shot():
    timing, info = music_cut_plan(np.zeros(10 * RATE, dtype=np.float32), RATE, duration=10, fps=24, mode="phrases")
    assert [row["duration_frames"] for row in timing["shots"]] == [240] and info["warnings"]
