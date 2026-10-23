"""Tempo and beat grid from a mono waveform (numpy only): spectral-flux onsets, autocorrelation tempo, best-fit phase."""
import wave
from pathlib import Path

import numpy as np

MIN_BPM = 60.0
MAX_BPM = 180.0
WINDOW = 2048
FINE_WINDOW = 256  # short window: its onsets are timed to within a few ms, the long one is better for tempo
BASS_WINDOW = 1024  # long enough to tell the kick from the hats (43 Hz per bin at 44.1 kHz)
BASS_HZ = 200.0


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        channels, width, rate, count = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(count)
    if width != 2:
        raise ValueError("Only 16-bit PCM wav files are supported")
    samples = np.frombuffer(raw, dtype="<i2").reshape(-1, channels).astype(np.float32) / 32768.0
    return samples.mean(axis=1), rate


def write_wav(path: Path, samples: np.ndarray, rate: int) -> None:
    """samples: [T, channels] float in -1..1."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def onset_envelope(samples: np.ndarray, rate: int, size: int = WINDOW, max_hz: float = 0.0) -> tuple[np.ndarray, float]:
    """Onset strength per hop and the hop length in seconds; max_hz > 0 keeps only the bins below that frequency."""
    hop = max(rate // 100, 1)
    if len(samples) < size + hop:
        return np.zeros(1, dtype=np.float32), hop / rate
    window = np.hanning(size).astype(np.float32)
    starts = np.arange(0, len(samples) - size, hop)
    frames = np.stack([samples[s : s + size] * window for s in starts])
    magnitude = np.abs(np.fft.rfft(frames, axis=1))
    if max_hz > 0:  # linear, not log: a kick is a few strong bins, a burst of noise is many weak ones
        magnitude = magnitude[:, 1 : max(int(max_hz * size / rate), 2)]
    else:
        magnitude = np.log1p(10.0 * magnitude)
    flux = np.maximum(magnitude[1:] - magnitude[:-1], 0.0).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    local = np.convolve(flux, np.ones(31) / 31, mode="same")
    return np.maximum(flux - local, 0.0).astype(np.float32), hop / rate


def estimate_bpm(env: np.ndarray, hop_seconds: float) -> float:
    env = env - env.mean()
    corr = np.correlate(env, env, mode="full")[len(env) - 1 :]
    lags = np.arange(len(corr))
    bpm = np.zeros(len(corr))
    bpm[1:] = 60.0 / (lags[1:] * hop_seconds)
    valid = (bpm >= MIN_BPM) & (bpm <= MAX_BPM)
    if not valid.any():
        return 120.0
    prior = np.exp(-0.5 * (np.log2(np.where(valid, bpm, 1.0) / 120.0) / 0.7) ** 2)  # people favour tempos near 120
    score = np.where(valid, corr * prior, -np.inf)
    lag = int(np.argmax(score))
    if 0 < lag < len(corr) - 1:  # parabolic refinement of the peak
        a, b, c = corr[lag - 1], corr[lag], corr[lag + 1]
        denom = a - 2 * b + c
        if denom != 0:
            lag = lag + 0.5 * (a - c) / denom
    return 60.0 / (lag * hop_seconds)


def detect_beats(samples: np.ndarray, rate: int, bpm: float = 0.0) -> tuple[float, np.ndarray]:
    """Return (bpm, beat times in seconds). bpm > 0 forces the tempo and only the phase is searched."""
    env, hop_seconds = onset_envelope(samples, rate)
    bpm = bpm if bpm > 0 else estimate_bpm(env, hop_seconds)
    fine, hop_seconds = onset_envelope(samples, rate, FINE_WINDOW)
    bass, _ = onset_envelope(samples, rate, BASS_WINDOW, BASS_HZ)  # the kick marks the beat; hats and claps on the off-beat pull the phase away from it
    period = 60.0 / bpm / hop_seconds  # in env frames
    phases = np.arange(0.0, period, 0.25)
    n = len(fine)

    def score(env: np.ndarray) -> np.ndarray:
        # tolerate a +-1 frame spread around each beat, a played tempo is never perfectly grid-aligned
        found = np.array([sum(env[np.round(np.arange(p, n, period) + d).astype(int).clip(0, n - 1)].sum() for d in (-1, 0, 1)) for p in phases])
        return found / found.max() if found.max() > 0 else found

    start = phases[int(np.argmax(score(fine) + 2 * score(np.pad(bass, (0, max(n - len(bass), 0))))))] * hop_seconds
    return bpm, np.arange(start, len(samples) / rate, 60.0 / bpm)
