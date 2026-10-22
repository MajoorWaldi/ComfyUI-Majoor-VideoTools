"""Hits of a music by frequency band (kick, snare, hi-hat), described shot by shot for the LLM that writes the prompts and the effects.

Numpy only. The hits come from the spectral flux of each band; the text tells which hits are worth a cut and which only deserve an effect."""
import numpy as np

from .errors import MajoorError
from .template import parse_plan
from .timeline_sources import rhythm_text

SIZE = 1024
# band name -> (low Hz, high Hz, minimum seconds between two hits)
BANDS = {"kick": (30.0, 150.0, 0.12), "snare": (150.0, 2500.0, 0.12), "hihat": (6000.0, 16000.0, 0.04)}
CUT_BANDS = ("kick", "snare")  # the hits that carry a cut; the hi-hat only gets effects
MAX_LISTED = 8


def band_hits(samples: np.ndarray, rate: int, sensitivity: float = 0.5) -> dict[str, list[tuple[float, float]]]:
    """(time in seconds, strength 0..1) of every hit, per band. Higher sensitivity keeps weaker hits."""
    if not 0.0 <= sensitivity <= 1.0:
        raise MajoorError("sensitivity must be between 0 and 1")
    hop = max(SIZE // 4, 1)
    if len(samples) < SIZE + hop:
        return {name: [] for name in BANDS}
    window = np.hanning(SIZE).astype(np.float32)
    starts = np.arange(0, len(samples) - SIZE, hop)
    frames = np.stack([samples[s : s + SIZE] * window for s in starts])
    magnitude = np.log1p(30.0 * np.abs(np.fft.rfft(frames, axis=1)))
    freqs = np.fft.rfftfreq(SIZE, 1.0 / rate)
    out: dict[str, list[tuple[float, float]]] = {}
    for name, (low, high, gap) in BANDS.items():
        cols = (freqs >= low) & (freqs < min(high, rate / 2))
        if not cols.any():
            out[name] = []
            continue
        flux = np.concatenate([[0.0], np.maximum(magnitude[1:, cols] - magnitude[:-1, cols], 0.0).sum(axis=1)])
        peak = flux.max()
        if peak <= 0:
            out[name] = []
            continue
        flux = flux / peak
        local = np.convolve(flux, np.ones(21) / 21, mode="same")
        threshold = local + (0.45 - 0.35 * sensitivity) * flux.std() * 4 + (0.25 - 0.2 * sensitivity)
        min_gap = max(int(gap * rate / hop), 1)
        found: list[list[float]] = []  # [frame, strength]
        for i in range(1, len(flux) - 1):
            if flux[i] >= flux[i - 1] and flux[i] > flux[i + 1] and flux[i] > threshold[i]:
                if found and i - found[-1][0] < min_gap:
                    if flux[i] > found[-1][1]:
                        found[-1] = [i, float(flux[i])]
                    continue
                found.append([i, float(flux[i])])
        out[name] = [((i * hop + SIZE / 2) / rate, strength) for i, strength in found]
    return out


def _listing(times: list[float]) -> str:
    """'every 0.50 s (x4)' for a regular pulse, else the times (relative to the shot start)."""
    if len(times) >= 3:
        gaps = np.diff(times)
        if gaps.std() <= 0.15 * gaps.mean():
            return f"every {gaps.mean():.2f} s (x{len(times)})"
    shown = ", ".join(f"{t:.2f}" for t in times[:MAX_LISTED])
    return f"at {shown}" + (f" (+{len(times) - MAX_LISTED} more)" if len(times) > MAX_LISTED else "")


def _loudness(samples: np.ndarray, rate: int, a: float, b: float) -> float:
    chunk = samples[int(a * rate) : max(int(b * rate), int(a * rate) + 1)]
    return float(np.sqrt(np.mean(chunk**2))) if len(chunk) else 0.0


def audio_lines(hits: dict[str, list[tuple[float, float]]], samples: np.ndarray, rate: int, windows: list[tuple[float, float]]) -> list[str]:
    """One line per window (start, end in seconds): the hits of each band and the loudness, to enrich the prompt and the effects."""
    reference = max(_loudness(samples, rate, 0.0, len(samples) / rate), 1e-9)
    lines = []
    for a, b in windows:
        parts = []
        for name in BANDS:
            times = [t - a for t, _ in hits[name] if a <= t < b]
            if times:
                parts.append(f"{name} {_listing(times)}")
        level = _loudness(samples, rate, a, b) / reference
        half = (a + b) / 2
        first, second = _loudness(samples, rate, a, half), _loudness(samples, rate, half, b)
        trend = "rising" if second > 1.25 * first else "falling" if first > 1.25 * second else "steady"
        mood = "loud" if level > 1.15 else "quiet" if level < 0.6 else "medium"
        hat = sum(1 for t, _ in hits["hihat"] if a <= t < b)
        advice = []
        if any(p.startswith(c) for p in parts for c in CUT_BANDS):
            advice.append("cuts can fall on the kick/snare")
        if hat >= 3:
            advice.append("hi-hat = texture: flash, zoom pulse or look changes, no cuts")
        lines.append(f"    audio: {mood}, {trend}" + (f" · {' · '.join(parts)}" if parts else " · no clear hit") + (f" → {'; '.join(advice)}" if advice else ""))
    return lines


def audio_rhythm_text(plan_text: str, fps: float, samples: np.ndarray, rate: int, sensitivity: float = 0.5) -> tuple[str, dict]:
    """The rhythm_text of a plan with the audio of each shot under its line. Returns (text, hits as {band: [seconds]})."""
    plan = parse_plan(plan_text, fps, "16:9", 64)
    frame_rate = float(plan.fps)
    hits = band_hits(samples, rate, sensitivity)
    windows, at = [], 0
    for shot in plan.shots:
        windows.append((at / frame_rate, (at + shot.frames) / frame_rate))
        at += shot.frames
    head, *shot_lines = rhythm_text(plan_text, fps).split("\n")
    out = [head]
    for line, extra in zip(shot_lines, audio_lines(hits, samples, rate, windows)):
        out += [line, extra]
    return "\n".join(out), {name: [round(t, 3) for t, _ in found] for name, found in hits.items()}
