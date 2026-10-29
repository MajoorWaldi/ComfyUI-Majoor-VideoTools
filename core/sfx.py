"""Local synthesized editorial cues, with Tone.js palette and procedural fallback.
No downloads during assembly; cue selection and mixing share the existing SFX bus.
"""
import numpy as np

from .errors import MajoorError

RATE = 48000
# the transition into a cut -> the sound under it; a plain cut that opens a shot is a soft "hit"
CUES = {"flash": "shutter", "flash_black": "impact", "fade_black": "swell", "fade_white": "swell", "whip": "whoosh", "whip_v": "whoosh", "blur": "whoosh",
        "punch": "hit", "glitch": "glitch", "shake": "hit", "strobe": "glitch", "invert": "impact"}
GAINS = {"shutter": 0.55, "impact": 0.85, "swell": 0.4, "whoosh": 0.6, "hit": 0.5, "glitch": 0.45}
# seconds before the cut where each sound starts, so that its weight lands on the cut: a whoosh peaks in the middle of its length, a swell near its end
LEAD = {"whoosh": 0.27, "swell": 0.72}
# what stays when two cues are closer than MIN_GAP: the heavier one
PRIORITY = {"impact": 5, "glitch": 4, "shutter": 4, "whoosh": 3, "swell": 3, "hit": 1}
GAINS.update(sub_drop=.32,riser=.22,reverse=.24,downlifter=.24,click=.20,pop=.22,tick=.15,sparkle=.18,tape_stop=.22,stutter=.22)
LEAD.update(riser=1.30,reverse=.61,whoosh=.275,swell=.79)
PRIORITY.update(sub_drop=5,riser=2,reverse=3,downlifter=3,click=1,pop=1,tick=1,sparkle=2,tape_stop=4,stutter=4)
GAINS.update(ui_click_soft=.16,ui_click_crisp=.16,notification_soft=.18,notification_confirm=.18,notification_alert=.16,metal_tick=.14,metal_chime=.18,glass_ping=.16,stereo_whoosh_lr=.38,stereo_whoosh_rl=.38,stereo_sweep=.30,logo_soft=.18,logo_bold=.22,logo_sparkle=.17)
LEAD.update(stereo_whoosh_lr=.30,stereo_whoosh_rl=.30,stereo_sweep=.425)
PRIORITY.update({kind:2 for kind in ('ui_click_soft','ui_click_crisp','notification_soft','notification_confirm','notification_alert','metal_tick','metal_chime','glass_ping','logo_soft','logo_bold','logo_sparkle')})
PRIORITY.update(stereo_whoosh_lr=3,stereo_whoosh_rl=3,stereo_sweep=3)
MIN_GAP = 0.4
HIT_REACH = 0.12  # a hit is played only when the music has an attack within this many seconds, and it goes onto that attack


def cue_balance(events, bus, music, rate, music_rate):
    """Cheap internal RMS diagnostic; deliberately no automatic gain correction."""
    groups=[]
    for at,kind in sorted(events):
        if groups and at-groups[-1][0][0]<=.15: groups[-1].append((at,kind))
        else: groups.append([(at,kind)])
    rows=[]
    for group in groups:
        at=group[0][0]
        sound=bus[max(0,round(at*rate)):min(len(bus),round((at+.4)*rate))]
        program=music[max(0,round((at-1)*music_rate)):min(len(music),round((at+2)*music_rate))]
        a=float(np.sqrt(np.mean(sound**2))) if len(sound) else 0.
        b=float(np.sqrt(np.mean(program**2))) if len(program) else 0.
        rows.append({'at':at,'kinds':sorted({k for _,k in group}),
                     'relative_rms_db':round(20*np.log10(max(a,1e-10)/b),2) if b>1e-8 else None,
                     'scope':'SFX versus music only; not LUFS or perceived audibility'})
    return rows


def _time(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * RATE)) / RATE


def _noise(seconds: float, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).uniform(-1.0, 1.0, int(seconds * RATE)).astype(np.float32)


def _low_pass(x: np.ndarray, cutoff: np.ndarray) -> np.ndarray:
    """A one-pole low-pass whose cutoff (Hz, one value per sample) moves: the sweep of a whoosh."""
    coefficient = 1.0 - np.exp(-2.0 * np.pi * np.clip(cutoff, 20.0, RATE / 2.5) / RATE)
    y = np.empty_like(x)
    state = 0.0
    for i in range(len(x)):
        state += coefficient[i] * (x[i] - state)
        y[i] = state
    return y


def _impact() -> np.ndarray:
    t = _time(0.9)
    sweep = np.sin(2.0 * np.pi * np.cumsum(95.0 + 150.0 * np.exp(-t / 0.06)) / RATE) * np.exp(-t / 0.22)  # above the sub of the music, which has its own
    body = _low_pass(_noise(0.9, 1), np.full(len(t), 900.0)) * np.exp(-t / 0.04) * 1.2
    return (0.9 * sweep + 0.5 * body).astype(np.float32)


def _hit() -> np.ndarray:
    t = _time(0.35)
    thump = np.sin(2.0 * np.pi * np.cumsum(160.0 + 130.0 * np.exp(-t / 0.03)) / RATE) * np.exp(-t / 0.07)  # a knock above the kick and the sub of the music
    click = _low_pass(_noise(0.35, 2), np.full(len(t), 4000.0)) * np.exp(-t / 0.012)
    return (0.9 * thump + 0.4 * click).astype(np.float32)


def _whoosh() -> np.ndarray:
    t = _time(0.55)
    position = t / t[-1]
    envelope = np.sin(np.pi * position) ** 2
    noise = _low_pass(_noise(0.55, 3), 300.0 + 6500.0 * position**1.5)
    return (noise * envelope * 1.4).astype(np.float32)


def _swell() -> np.ndarray:
    t = _time(0.8)
    position = t / t[-1]
    noise = _low_pass(_noise(0.8, 4), 200.0 + 3000.0 * position**2)
    return (noise * position**2 * np.exp(-((position - 1.0) ** 2) / 0.05) * 1.5).astype(np.float32)


def _shutter() -> np.ndarray:
    out = np.zeros(int(0.35 * RATE), np.float32)
    for k, (at, length, seed) in enumerate(((0.0, 0.012, 5), (0.045, 0.03, 6))):  # the two clicks of a camera
        click = _low_pass(_noise(length, seed), np.full(int(length * RATE), 7000.0 - 3000.0 * k)) * np.exp(-_time(length) / (length / 3))
        start = int(at * RATE)
        out[start:start + len(click)] += click * (1.2 if k == 0 else 1.0)
    return out


def _glitch() -> np.ndarray:
    t = _time(0.22)
    stutter = (np.sin(2.0 * np.pi * 3200.0 * t) * np.sign(np.sin(2.0 * np.pi * 38.0 * t))).astype(np.float32)
    crushed = np.round(_noise(0.22, 7) * 4.0) / 4.0
    return ((0.5 * stutter + 0.5 * crushed) * np.exp(-t / 0.09)).astype(np.float32)


_MAKERS = {"impact": _impact, "hit": _hit, "whoosh": _whoosh, "swell": _swell, "shutter": _shutter, "glitch": _glitch}
_CACHE: dict[str, np.ndarray] = {}


def cue_sound(kind: str) -> np.ndarray:
    """The mono/stereo sound of a cue at RATE, normalized to a peak of 1 (the same array every time: it is made once and kept)."""
    from .tone_sfx import tone_library
    palette,_ = tone_library()
    if kind in palette:
        return palette[kind]
    kind = {'sub_drop':'impact','riser':'swell','reverse':'swell','downlifter':'whoosh','click':'shutter','pop':'hit','tick':'shutter','sparkle':'shutter','tape_stop':'glitch','stutter':'glitch','ui_click_soft':'shutter','ui_click_crisp':'shutter','notification_soft':'hit','notification_confirm':'hit','notification_alert':'hit','metal_tick':'shutter','metal_chime':'hit','glass_ping':'hit','stereo_whoosh_lr':'whoosh','stereo_whoosh_rl':'whoosh','stereo_sweep':'whoosh','logo_soft':'hit','logo_bold':'hit','logo_sparkle':'hit'}.get(kind,kind)
    if kind not in _MAKERS:
        raise MajoorError(f"Unknown sound effect '{kind}'. Available: {list(_MAKERS)}")
    if kind not in _CACHE:
        sound = _MAKERS[kind]()
        _CACHE[kind] = sound / max(float(np.abs(sound).max()), 1e-6)
    return _CACHE[kind]


def plan_cues(events: list[tuple[float, str]], accents=None) -> list[tuple[float, str]]:
    """The cues that are worth playing: a hit only where the music has an attack (and onto it), and no two cues closer than MIN_GAP (the heavier one stays)."""
    kept = []
    for start, kind in sorted(events):
        if kind in ('hit','click','pop','tick') and accents is not None and len(accents):
            near = float(accents[int(np.abs(accents - start).argmin())])
            if abs(near - start) > HIT_REACH:
                continue
            start = near
        kept.append((start, kind))
    out: list[tuple[float, str]] = []
    for start, kind in kept:
        if out and start - out[-1][0] < MIN_GAP:
            if PRIORITY[kind] > PRIORITY[out[-1][1]]:
                out[-1] = (start, kind)
            continue
        out.append((start, kind))
    return out


def render_track(events: list[tuple[float, str]], seconds: float, library: dict[str,np.ndarray] | None = None, level: float = 1.0, generated: set[str] | None = None, *, anchors=None) -> np.ndarray:
    """The stereo track [T, 2] of the cues (the time of the cut, kind), as long as the edit; a sound that leads into a cut starts before it (LEAD). `level` follows the loudness of the music.
    A cue is panned a little to one side, then the other, so that a series does not stack on the centre."""
    track = np.zeros((int(seconds * RATE), 2), np.float32)
    for n, (start, kind) in enumerate(events):
        sound = (library[kind] if library and kind in library else cue_sound(kind)) * GAINS[kind] * level
        user_sample = library and kind in library and kind not in (generated or set())
        lead = 0.0 if user_sample else LEAD.get(kind, 0.0)
        if not user_sample and anchors and kind in anchors:
            anchor = anchors[kind]
            if isinstance(anchor, bool) or not isinstance(anchor, int) or not 0 <= anchor < len(sound):
                raise MajoorError('Sound anchor must be a sample inside its waveform')
            lead = anchor / RATE
        offset = round((start - lead) * RATE)
        skip = max(-offset, 0)
        sound = sound[skip:]
        begin = max(offset, 0)
        end = min(begin + len(sound), len(track))
        if begin >= len(track) or end <= begin:
            continue
        pan = 0.5 + (0.12 if n % 2 else -0.12)
        part=sound[:end-begin]
        if sound.ndim==2 and sound.shape[1]==2:
            track[begin:end] += part * .7  # retain designed stereo movement
        else:
            track[begin:end, 0] += part * (1.0 - pan) * 1.4
            track[begin:end, 1] += part * pan * 1.4
    # Conservative SFX bus headroom; the final assembly also limits the complete mix.
    return np.tanh(track * 0.32).astype(np.float32)
