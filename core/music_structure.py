"""The shape of a track: sections (intro, build, drop, break, outro) from its loudness, and the downbeat among its beats. Measured, no model."""
import numpy as np

from .beats import WINDOW, onset_envelope

TAGS = ("intro", "build", "drop", "break", "outro")


def _levels(samples, rate, hop_seconds=.5):
    hop = max(1, round(rate * hop_seconds))
    levels = np.array([np.sqrt(np.mean(c.astype(np.float64) ** 2)) for s in range(0, len(samples), hop) if len(c := samples[s:s + hop])])
    peak = levels.max() if len(levels) else 0
    return levels / peak if peak > 0 else levels, hop / rate


def track_sections(samples, rate, hop_seconds=.5, min_seconds=2.0) -> list[dict]:
    """[{"tag", "start", "end"}] covering the track. A drop is where the loudness jumps up to its high level after a quieter stretch, a break where it falls away after one."""
    levels, hop = _levels(np.asarray(samples), rate, hop_seconds)
    if len(levels) < 4:
        return [{"tag": "intro", "start": 0.0, "end": round(len(samples) / rate, 3)}]
    smooth = np.convolve(levels, np.ones(3) / 3, mode="same")
    high, low = .75 * smooth.max(), .45 * smooth.max()
    state = ["high" if v >= high else "low" if v < low else "mid" for v in smooth]
    runs, begin = [], 0
    for i in range(1, len(state) + 1):
        if i == len(state) or state[i] != state[begin]:
            runs.append([state[begin], begin, i])
            begin = i
    merged = []
    for run in runs:  # runs shorter than min_seconds join the run before them
        if merged and (run[2] - run[1]) * hop < min_seconds:
            merged[-1][2] = run[2]
        elif merged and merged[-1][0] == run[0]:
            merged[-1][2] = run[2]
        else:
            merged.append(run)
    sections = []
    for i, (kind, a, b) in enumerate(merged):
        before = merged[i - 1][0] if i else None
        if i == 0:
            tag = "intro"
        elif i == len(merged) - 1 and kind != "high":
            tag = "outro"
        elif kind == "high":
            tag = "drop"
        elif kind == "low" and before == "high":
            tag = "break"
        else:
            tag = "build"
        sections.append({"tag": tag, "start": round(a * hop, 3), "end": round(min(b * hop, len(samples) / rate), 3)})
    return sections


def drop_times(sections) -> list[float]:
    return [s["start"] for s in sections if s["tag"] == "drop"]


def find_downbeats(samples, rate, beats, beats_per_bar=4) -> list[float]:
    """The beats that open a bar: of the `beats_per_bar` possible phases, the one whose beats carry the most low-frequency energy."""
    beats = [float(b) for b in beats]
    if len(beats) < beats_per_bar:
        return beats[:1]
    env, hop = onset_envelope(np.asarray(samples), rate, max_hz=200.0)
    # a long window sees an attack before it starts, so look from one window before the beat to just after it
    at = [env[max(int((b - WINDOW / rate) / hop), 0):max(int((b + .05) / hop), 1) + 1].max() for b in beats]
    phase = max(range(beats_per_bar), key=lambda p: sum(at[p::beats_per_bar]) / len(at[p::beats_per_bar]))
    return beats[phase::beats_per_bar]
