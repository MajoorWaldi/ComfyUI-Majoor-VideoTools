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


def align_grid_to_onsets(grid: list[int], samples: np.ndarray, rate: int, fps: float, max_shift_frames: int = 2) -> list[int]:
    """Refine a cut grid toward nearby audible attacks; never invent or reorder beats.

    This is a local timing correction, not a new tempo estimate. Weak attacks,
    silence and points without a nearby peak retain their original position.
    """
    if not grid or max_shift_frames <= 0:
        return list(grid)
    env, hop = onset_envelope(samples, rate, FINE_WINDOW)
    if len(env) < 3 or float(env.max()) <= 1e-8:
        return list(grid)
    peaks = np.flatnonzero((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:])) + 1
    peaks = peaks[env[peaks] >= float(env.max()) * 0.15]
    # Flux timestamps describe analysis-window starts; use the window centre.
    frames = np.unique(np.rint((peaks * hop + FINE_WINDOW / (2 * rate)) * fps).astype(int))
    refined = []
    for i, point in enumerate(grid):
        nearby = frames[np.abs(frames - point) <= max_shift_frames]
        # Keep strict ordering with both already refined and upcoming grid points.
        lower = refined[-1] if refined else -1
        upper = grid[i + 1] if i + 1 < len(grid) else np.inf
        nearby = nearby[(nearby > lower) & (nearby < upper)]
        target = int(nearby[np.argmin(np.abs(nearby - point))]) if len(nearby) else point
        refined.append(target)
    return refined


def strong_accents(samples: np.ndarray, rate: int, min_ratio: float = 0.3) -> tuple[np.ndarray, np.ndarray]:
    """The audible attacks of a music: their times in seconds and their strength (0 to 1; 1 is the level of the strongest tenth of the attacks). Attacks closer than 60 ms keep the stronger one."""
    broad, hop = onset_envelope(samples, rate, FINE_WINDOW)
    low, _ = onset_envelope(samples, rate, FINE_WINDOW, max_hz=200.0)  # the kick and the sub carry the pulse that a cut is felt on
    if len(broad) < 3 or float(broad.max()) <= 1e-8:
        return np.zeros(0), np.zeros(0)

    def level(env: np.ndarray) -> np.ndarray:
        found = np.flatnonzero((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:])) + 1
        return env / max(float(np.percentile(env[found], 90)) if len(found) else float(env.max()), 1e-8)  # a few huge hits (a 808, a crash) must not make every kick look weak: 1 is the top tenth of the attacks

    env = np.maximum(0.6 * level(broad), level(low))
    peaks = np.flatnonzero((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:])) + 1
    if not len(peaks):
        return np.zeros(0), np.zeros(0)
    strength = np.minimum(env[peaks], 1.0)
    peaks, strength = peaks[strength >= min_ratio], strength[strength >= min_ratio]
    times = peaks * hop + FINE_WINDOW / (2 * rate)  # flux timestamps describe analysis-window starts: use the window centre
    keep: list[int] = []
    for i in range(len(times)):
        if keep and times[i] - times[keep[-1]] < 0.06:
            if strength[i] > strength[keep[-1]]:
                keep[-1] = i
            continue
        keep.append(i)
    return times[keep], strength[keep]


def accent_candidates(times: np.ndarray, strength: np.ndarray, fps: float, floor: float = 0.5) -> dict[int, float]:
    """The frames of the attacks themselves with their strength: a cut may go straight to one even where the tempo grid is a little off."""
    out: dict[int, float] = {}
    for t, s in zip(times, strength):
        if s >= floor:
            frame = int(round(float(t) * fps))
            out[frame] = max(out.get(frame, 0.0), float(s))
    return out


def accent_strength(frames, times: np.ndarray, strength: np.ndarray, fps: float, radius: int = 2) -> dict[int, float]:
    """For each frame of a cut grid, the strength of the strongest attack within `radius` frames of it (0 when there is none)."""
    attack_frames = np.rint(times * fps).astype(int)
    out = {}
    for frame in frames:
        near = np.abs(attack_frames - frame) <= radius
        out[int(frame)] = float(strength[near].max()) if near.any() else 0.0
    return out


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        channels, width, rate, count = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(count)
    if width != 2:
        raise ValueError("Only 16-bit PCM wav files are supported")
    samples = np.frombuffer(raw, dtype="<i2").reshape(-1, channels).astype(np.float32) / 32768.0
    return samples.mean(axis=1), rate


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """The samples of a 16-bit PCM wav file as [T, channels] floats in -1..1."""
    with wave.open(str(path), "rb") as w:
        channels, width, rate, count = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(count)
    if width != 2:
        raise ValueError("Only 16-bit PCM wav files are supported")
    return np.frombuffer(raw, dtype="<i2").reshape(-1, channels).astype(np.float32) / 32768.0, rate


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
    flux = np.zeros(len(starts), dtype=np.float32)
    view = np.lib.stride_tricks.sliding_window_view(samples,size)[::hop][:len(starts)]
    previous = None
    for offset in range(0,len(starts),512):
        magnitude = np.abs(np.fft.rfft(view[offset:offset+512]*window,axis=1))
        if max_hz > 0:
            magnitude = magnitude[:,1:max(int(max_hz*size/rate),2)]
        else:
            magnitude = np.log1p(10.0*magnitude)
        if previous is not None:
            flux[offset] = np.maximum(magnitude[0]-previous,0).sum()
        flux[offset+1:offset+len(magnitude)] = np.maximum(magnitude[1:]-magnitude[:-1],0).sum(axis=1)
        previous = magnitude[-1]
    local = np.convolve(flux, np.ones(31) / 31, mode="same")
    return np.maximum(flux - local, 0.0).astype(np.float32), hop / rate


def estimate_bpm(env: np.ndarray, hop_seconds: float) -> float:
    env = env - env.mean()
    size = 1 << (2*len(env)-1).bit_length()
    spectrum = np.fft.rfft(env,n=size)
    corr = np.fft.irfft(spectrum*spectrum.conjugate(),n=size)[:len(env)]
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


def _detect_grid(samples: np.ndarray, rate: int, bpm: float = 0.0) -> tuple[float, np.ndarray]:
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


def analyze_rhythm(samples: np.ndarray, rate: int, bpm: float = 0.0) -> dict:
    """Qualify a grid. Confidence is a heuristic, not a calibrated probability."""
    samples = np.asarray(samples)
    if samples.ndim != 1 or rate <= 0 or not np.isfinite(samples).all() or not np.isfinite(bpm) or bpm < 0:
        raise ValueError('Rhythm needs finite mono audio, a positive sample rate and a nonnegative tempo')
    env, hop = onset_envelope(samples, rate)
    centered = env - env.mean()
    power = float(np.dot(centered, centered))
    active = len(samples) >= rate and float(np.max(env)) > 1e-4 and power > 1e-8
    confidence = 0.
    candidate = float(bpm) if bpm > 0 else (estimate_bpm(env, hop) if active else None)
    if active and candidate:
        lag = max(1, round(60 / candidate / hop))
        if lag < len(centered):
            confidence = float(np.clip(np.dot(centered[:-lag], centered[lag:]) / power, 0, 1))
    if bpm <= 0 and (candidate is None or confidence < .15):
        return {'status': 'no_reliable_pulse', 'bpm': None, 'beats': np.zeros(0),
                'tempo_confidence': confidence, 'phase_confidence': 0., 'timing_source': 'none'}
    found, beats = _detect_grid(samples, rate, candidate)
    return {'status': 'user_tempo' if bpm > 0 else 'estimated', 'bpm': found, 'beats': beats,
            'tempo_confidence': confidence, 'phase_confidence': confidence,
            'timing_source': 'user_grid' if bpm > 0 else 'measured'}


def detect_beats(samples: np.ndarray, rate: int, bpm: float = 0.0) -> tuple[float, np.ndarray]:
    """Compatible tuple; 0 BPM and empty beats denotes no reliable pulse."""
    analysis = analyze_rhythm(samples, rate, bpm)
    return analysis['bpm'] or 0., analysis['beats']
