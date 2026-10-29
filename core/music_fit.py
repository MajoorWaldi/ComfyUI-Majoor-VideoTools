"""Cut a long music to the length of an edit, on the bars: the window starts on a downbeat, on the strongest part (a drop) unless a start is given, and the music is looped by whole bars when it is too short.

Numpy only. The tempo and the beats come from core.beats (the phase follows the kick); the first beat of a bar is the one whose beats hit the bass hardest."""
import numpy as np

from .beats import BASS_HZ, BASS_WINDOW, FINE_WINDOW, analyze_rhythm, onset_envelope
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


def fit_music(samples: np.ndarray, rate: int, length: float, bpm: float = 0.0, start: float = -1.0, beats_per_bar: int = 4, energy_goal: str = 'peak',moments: list | None = None) -> tuple[np.ndarray, dict]:
    """samples: [T, channels] in -1..1. Returns the [length * rate, channels] window and what was chosen (bpm, start in seconds, bars, whether it was looped)."""
    if length <= 0:
        raise MajoorError("The length of the edit must be above 0 seconds")
    if energy_goal not in ('peak','calm','balanced','intense'):
        raise MajoorError('Unknown music energy goal')
    moments=moments or []
    if not isinstance(moments,list) or any(not isinstance(m,dict) or not isinstance(m.get('at'),(int,float)) or not 0<=m['at']<=length or not isinstance(m.get('strength',1),(int,float)) or not 0<=m.get('strength',1)<=1 for m in moments):
        raise MajoorError('Music moments need times inside the edit and strengths between0and1')
    mono = samples.mean(axis=1)
    rhythm = analyze_rhythm(mono, rate, bpm)
    bpm, beats = rhythm['bpm'], rhythm['beats']
    if bpm is None:
        if len(mono) < rate * 2:
            raise MajoorError('The music is too short to choose a usable window')
        begin = min(max(round(max(start, 0) * rate), 0), len(samples) - 1)
        wanted = max(round(length * rate), 1)
        out = samples[begin:begin + wanted].copy()
        out = np.pad(out, ((0, max(0, wanted - len(out))), (0, 0)))
        fade_in = min(round(FADE_IN * rate), len(out))
        out[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
        fade = min(round(FADE_OUT * rate), len(out))
        out[-fade:] *= np.linspace(1, 0, fade)[:, None]
        return out, {'bpm': None, 'start': begin / rate, 'bars': None, 'looped': False,
                     'music_seconds': len(mono) / rate, 'energy_goal': energy_goal,
                     'accent_matches': [], 'timing_source': 'none',
                     'warnings': ['No reliable pulse; retained window without bar alignment or looping']}
    if len(beats) < beats_per_bar * 2:
        raise MajoorError(f"Only {len(beats)} beats found in {len(mono) / rate:.1f} s of music: it is too short to be cut on its bars")
    bars = _downbeats(mono, rate, beats, beats_per_bar)
    bar_length = 60.0 / bpm * beats_per_bar
    total = len(mono) / rate
    looped = total - bars[0] < length
    if looped:
        complete = bars[bars + bar_length <= total + 1e-9]
        if not len(complete):
            raise MajoorError('The music contains no complete bar to loop')
        first = float(complete[int(np.argmin(np.abs(complete - start)))]) if start >= 0 else float(complete[0])
        if start < 0 and (energy_goal != 'peak' or moments):
            lengths = [max(int(np.floor((total-b)/bar_length+1e-9)), 1)*bar_length for b in complete]
            levels = np.array([_rms(mono, rate, b, b+span) for b, span in zip(complete, lengths)])
            normalized = (levels-levels.min())/max(float(np.ptp(levels)), 1e-8)
            target = {'calm': 0., 'balanced': .5, 'intense': 1., 'peak': 1.}[energy_goal]
            scores = -np.abs(normalized-target)
            if moments:
                envelope, hop = onset_envelope(mono, rate, FINE_WINDOW)
                ceiling = max(float(envelope.max()), 1e-8)
                radius = max(round(.12/hop), 1)
                for i, (b, span) in enumerate(zip(complete, lengths)):
                    for moment in moments:
                        point = round((b + moment['at'] % span)/hop)
                        part = envelope[max(0,point-radius):min(len(envelope),point+radius+1)]
                        if len(part): scores[i] += 1.5*float(part.max())/ceiling*moment.get('strength',1)/len(moments)
            first = float(complete[int(np.argmax(scores))])
        count = max(int(np.floor((total - first) / bar_length + 1e-9)), 1)
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
            if energy_goal!='peak':
                levels=np.array([_rms(mono,rate,b,b+length) for b in fits])
                normalized=(levels-levels.min())/max(float(np.ptp(levels)),1e-8)
                target={'calm':0.0,'balanced':.5,'intense':1.0}[energy_goal]
                scores=(-np.abs(normalized-target)).tolist()
            if moments:
                envelope,hop=onset_envelope(mono,rate,FINE_WINDOW)
                ceiling=max(float(envelope.max()),1e-8)
                radius=max(round(.12/hop),1)
                def accent(b,m):
                    point=round((b-PRE_ROLL+m['at'])/hop)
                    part=envelope[max(point-radius,0):min(point+radius+1,len(envelope))]
                    return float(part.max())/ceiling*m.get('strength',1) if len(part) else 0
                scale=max(max(abs(float(s)) for s in scores),1e-8)
                scores=[float(s)/scale+1.5*sum(accent(b,m) for m in moments)/len(moments) for b,s in zip(fits,scores)]
            chosen = float(fits[int(np.argmax(scores))])
        begin = max(int((chosen - PRE_ROLL) * rate), 0)
        samples_out = samples[begin : begin + int(round(length * rate))]
    samples_out = samples_out.copy()
    wanted = int(round(length * rate))
    if len(samples_out) < wanted:
        samples_out = np.pad(samples_out, ((0, wanted - len(samples_out)), (0, 0)))
    fade_in, fade_out = min(int(FADE_IN * rate), len(samples_out)), min(int(FADE_OUT * rate), len(samples_out))
    samples_out[:fade_in] *= np.linspace(0.0, 1.0, fade_in)[:, None]
    samples_out[-fade_out:] *= np.linspace(1.0, 0.0, fade_out)[:, None]
    matches=[]
    if moments:
        envelope,hop=onset_envelope(samples_out.mean(axis=1),rate,FINE_WINDOW)
        ceiling=max(float(envelope.max()),1e-8)
        for moment in moments:
            point=round(moment['at']/hop);radius=max(round(.35/hop),1)
            begin=max(point-radius,0);part=envelope[begin:min(point+radius+1,len(envelope))]
            peak=int(np.argmax(part)) if len(part) else 0
            found=(begin+peak)*hop if len(part) and float(part[peak])/ceiling>.1 else None
            matches.append({'at':moment['at'],'nearest_onset':found,'error_seconds':abs(found-moment['at']) if found is not None else None})
    return samples_out, {"bpm": round(float(bpm), 2), "start": round(chosen, 3), "bars": round(float(length / bar_length), 2), "looped": bool(looped), "music_seconds": round(float(total), 1),'energy_goal':energy_goal,'accent_matches':matches}
