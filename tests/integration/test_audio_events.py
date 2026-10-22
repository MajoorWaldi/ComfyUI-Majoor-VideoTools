import json

import numpy as np

from majoor_videotools.core.audio_events import audio_rhythm_text, band_hits

RATE = 44100


def _track(seconds=4.0):
    """Kick (60 Hz thump) on every beat of 120 BPM, hi-hat (noise above 7 kHz) on every eighth of a second."""
    t = np.arange(int(seconds * RATE)) / RATE
    out = np.zeros_like(t)
    for at in np.arange(0, seconds, 0.5):
        i = int(at * RATE)
        n = int(0.12 * RATE)
        out[i : i + n] += 0.8 * np.sin(2 * np.pi * 60 * t[:n]) * np.exp(-t[:n] * 30)
    rng = np.random.default_rng(0)
    for at in np.arange(0.0625, seconds, 0.125):
        i = int(at * RATE)
        n = int(0.02 * RATE)
        burst = np.fft.irfft(np.where(np.fft.rfftfreq(n, 1 / RATE) > 7000, rng.normal(size=n // 2 + 1), 0), n)
        out[i : i + n] += 0.5 * burst / max(np.abs(burst).max(), 1e-9) * np.exp(-np.arange(n) / (0.004 * RATE))
    return out.astype(np.float32)


def test_bands_find_their_own_hits():
    hits = band_hits(_track(), RATE)
    kicks = [t for t, _ in hits["kick"]]
    hats = [t for t, _ in hits["hihat"]]
    assert 6 <= len(kicks) <= 9 and all(abs(t / 0.5 - round(t / 0.5)) < 0.1 for t in kicks)
    assert 24 <= len(hats) <= 36 and len(hits["hihat"]) > 2 * len(hits["kick"])


def test_text_tells_what_to_cut_and_what_to_dress():
    plan = json.dumps({"fps": 24, "shots": [{"duration": 2.0, "prompt": ""}, {"duration": 2.0, "prompt": ""}]})
    text, hits = audio_rhythm_text(plan, 24, _track(), RATE)
    lines = text.split("\n")
    assert lines[0].startswith("EDIT RHYTHM: 2 shots") and lines[2].startswith("    audio:") and lines[4].startswith("    audio:")
    assert "kick every 0.50 s" in lines[2] and "hihat" in lines[2] and "no cuts" in lines[2]
    assert set(hits) == {"kick", "snare", "hihat"}
