"""Cut a long music to the length of an edit, on the bars: the window starts on a downbeat, on the strongest part (a drop) unless a start is given, and the music is looped by whole bars when it is too short.

Numpy only. The tempo and the beats come from core.beats (the phase follows the kick); the first beat of a bar is the one whose beats hit the bass hardest."""
import numpy as np

from .beats import BASS_HZ, BASS_WINDOW, detect_beats, onset_envelope
from .errors import MajoorError

PRE_ROLL = 0.02  # seconds kept before the downbeat so that the attack of the kick is not cut
FADE_IN = 0.005
FADE_OUT = 0.08


def _downbeats(mono: np.ndarray, rate: int, beats: np.ndarray, beats_per_bar: int) -> np.ndarray:
    """The beats that start a bar: of the beats_per_bar possible phases, the one where the bass onsets are strongest."""
    env, hop = onset_envelope(mono, rate, BASS_WINDOW, BASS_HZ)
    index = np.clip(np.round(beats / hop).astype(int), 0, len(env) - 1)
    scores = [env[index[phase::beats_per_bar]].sum() for phase in range(beats_per_bar)]
    return beats[int(np.argmax(scores)) :: beats_per_bar]


def _rms(mono: np.ndarray, rate: int, start: float, end: float) -> float:
    part = mono[max(int(start * rate), 0) : int(end * rate)]
    return float(np.sqrt(np.mean(part**2))) if len(part) else 0.0


def fit_music(samples: np.ndarray, rate: int, length: float, bpm: float = 0.0, start: float = -1.0, beats_per_bar: int = 4) -> tuple[np.ndarray, dict]:
    """samples: [T, channels] in -1..1. Returns the [length * rate, channels] window and what was chosen (bpm, start in seconds, bars, whether it was looped)."""
    if length <= 0:
        raise MajoorError("The length of the edit must be above 0 seconds")
    mono = samples.mean(axis=1)
    bpm, beats = detect_beats(mono, rate, bpm)
    if len(beats) < beats_per_bar * 2:
        raise MajoorError(f"Only {len(beats)} beats found in {len(mono) / rate:.1f} s of music: it is too short to be cut on its bars")
    bars = _downbeats(mono, rate, beats, beats_per_bar)
    bar_length = 60.0 / bpm * beats_per_bar
    total = len(mono) / rate
    looped = total - bars[0] < length
    if looped:
        first = float(bars[0])
        count = max(int(round((total - first) / bar_length)), 1)  # whole bars of the music
        loop = samples[int(first * rate) : int((first + count * bar_length) * rate)]
        repeats = int(np.ceil((length + PRE_ROLL) * rate / len(loop))) + 1
        window = np.tile(loop, (repeats, 1))
        chosen = first
        samples_out = window[: int(round(length * rate))]
    else:
        fits = bars[bars + length <= total]
        if not len(fits):
            fits = bars[:1]
        if start >= 0:
            chosen = float(fits[int(np.argmin(np.abs(fits - start)))])
        else:
            # the loudest window, and a bonus for a start that is louder than the bar before it: a drop, not the end of a fade
            scores = [_rms(mono, rate, b, b + length) + 0.5 * max(_rms(mono, rate, b, b + bar_length) - _rms(mono, rate, b - bar_length, b), 0.0) for b in fits]
            chosen = float(fits[int(np.argmax(scores))])
        begin = max(int((chosen - PRE_ROLL) * rate), 0)
        samples_out = samples[begin : begin + int(round(length * rate))]
    samples_out = samples_out.copy()
    wanted = int(round(length * rate))
    if len(samples_out) < wanted:
        samples_out = np.pad(samples_out, ((0, wanted - len(samples_out)), (0, 0)))
    fade_in, fade_out = int(FADE_IN * rate), int(FADE_OUT * rate)
    samples_out[:fade_in] *= np.linspace(0.0, 1.0, fade_in)[:, None]
    samples_out[-fade_out:] *= np.linspace(1.0, 0.0, fade_out)[:, None]
    return samples_out, {"bpm": round(float(bpm), 2), "start": round(chosen, 3), "bars": round(float(length / bar_length), 2), "looped": bool(looped), "music_seconds": round(float(total), 1)}
