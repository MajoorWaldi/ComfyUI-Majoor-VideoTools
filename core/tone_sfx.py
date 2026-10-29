"""Read a pre-rendered local Tone.js palette. No runtime downloads or browser launch."""
import hashlib
import json
import os
import random
import wave
from pathlib import Path
import numpy as np
from .errors import MajoorError

KINDS=('impact','hit','whoosh','swell','shutter','glitch','sub_drop','riser','reverse','downlifter','click','pop','tick','sparkle','tape_stop','stutter','ui_click_soft','ui_click_crisp','notification_soft','notification_confirm','notification_alert','metal_tick','metal_chime','glass_ping','stereo_whoosh_lr','stereo_whoosh_rl','stereo_sweep','logo_soft','logo_bold','logo_sparkle')
_CACHE={}
def bank_path():
    return Path(os.environ.get('MAJOOR_TONE_RUNTIME',Path(__file__).resolve().parents[1]/'runtime/tonejs'))/'bank'

def _read_tone_library():
    root=bank_path();manifest=root/'tone.json'
    if not manifest.is_file():return {},'procedural-v1'
    payload=manifest.read_bytes();key=hashlib.sha256(payload).hexdigest()
    # Content signatures participate in cache identity, not just file names.
    data=json.loads(payload)
    if data.get('engine')!='tone.js' or data.get('version')!='15.1.22' or not set(KINDS[:16]) <= set(data.get('entries',{})) <= set(KINDS):
        raise MajoorError('Invalid Tone.js palette; run scripts/install_tone.ps1')
    names=tuple(data['entries'])
    signatures=tuple((name,(root/(name+'.wav')).stat().st_mtime_ns) for name in names)
    cache_key=(str(root),key,signatures)
    if cache_key in _CACHE:return _CACHE[cache_key]
    sounds={}
    for name in names:
        path=root/(name+'.wav');raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=data['entries'][name]['sha256']:
            raise MajoorError(f'Changed Tone.js cue {name}; rebuild the palette')
        with wave.open(str(path),'rb') as wav:
            channels=wav.getnchannels()
            if channels not in (1,2) or (wav.getsampwidth(),wav.getframerate())!=(2,48000):
                raise MajoorError('Tone.js cues must be mono/stereo PCM16 at 48 kHz')
            samples=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(np.float32)/32768
            if channels==2:samples=samples.reshape(-1,2)
            sounds[name]=samples/max(float(np.abs(samples).max()),1e-6)
    _CACHE.clear();_CACHE[cache_key]=(sounds,'tone-'+key)
    return _CACHE[cache_key]

def tone_library_status():
    """Optional bank: untrusted or incomplete files never reach the mixer."""
    try:
        if not (bank_path() / 'tone.json').is_file():
            return {}, 'procedural-v1', 'optional:tone:missing'
        sounds, key = _read_tone_library()
        return sounds, key, None
    except (OSError, ValueError, TypeError, KeyError, AttributeError, EOFError, wave.Error, MajoorError):
        return {}, 'procedural-v1', 'optional:tone:unavailable'


def tone_library():
    sounds, key, _ = tone_library_status()
    return sounds, key


PALETTES = {
    'subtle': {'hit': ('ui_click_soft', 'tick'), 'whoosh': ('stereo_sweep',), 'impact': ('hit',)},
    'electronic': {'hit': ('ui_click_crisp', 'pop', 'tick'), 'whoosh': ('stereo_whoosh_lr', 'stereo_whoosh_rl')},
    'metallic': {'hit': ('metal_tick', 'metal_chime', 'hit'), 'whoosh': ('stereo_sweep',)},
}


def design_cues(events,seconds,overrides=(),available=None, *, preparations=None, palette=None, seed=0):
    """Choose a bounded palette from actual editorial cues, never infer physical actions."""
    dense=len(events)/max(seconds,1)>.7
    result=[];hit=0;last_build=-10
    counts={}
    if palette is not None and palette not in PALETTES:
        raise MajoorError('Unknown sound palette')
    rng = random.Random(seed)
    previous = {}
    for at,kind in events:
        if kind in overrides:
            result.append((at,kind));continue
        counts[kind]=counts.get(kind,0)+1
        if palette and kind in PALETTES[palette]:
            choices = [k for k in PALETTES[palette][kind] if available is None or k in available]
            alternatives = [k for k in choices if k != previous.get(kind)]
            selected = rng.choice(alternatives or choices) if choices else kind
            previous[kind] = selected
            kind = selected
        elif kind=='hit':
            choices=('hit','ui_click_crisp','pop','metal_tick','tick','ui_click_soft') if dense else ('hit','ui_click_soft','metal_tick')
            kind=choices[hit%len(choices)];hit+=1
        elif kind=='swell':kind=('reverse','downlifter')[counts[kind]%2]
        elif kind=='whoosh':kind=('stereo_whoosh_lr','stereo_whoosh_rl','downlifter' if dense else 'stereo_sweep')[(counts[kind]-1)%3]
        elif kind=='impact' and dense and counts[kind]%3==0:kind='sub_drop'
        elif kind=='glitch':kind='stutter' if dense else 'glitch'
        result.append((at,kind))
        # A short lead only before an already planned strong transition, at most once/6 s.
        if kind=='impact' and at>=2 and at-last_build>=6:
            landing = at if preparations is not None else at-.06
            result.append((landing,'riser'));last_build=at
            if preparations is not None:
                preparations[(landing,'riser')] = (at,'impact')
    # With a legacy bank, select only its available cues, preserving old installations.
    aliases={'ui_click_soft':'click','ui_click_crisp':'click','metal_tick':'tick','stereo_whoosh_lr':'whoosh','stereo_whoosh_rl':'whoosh','stereo_sweep':'whoosh'}
    if available is not None:
        result=[(at,kind if kind in available or kind in overrides else aliases.get(kind,'hit')) for at,kind in result]
    return sorted(result)


def tone_anchors():
    """Optional PCM48k anchors; old banks keep their historical LEAD values."""
    try:
        manifest = bank_path() / 'tone.json'
        if not manifest.is_file(): return {}
        entries = json.loads(manifest.read_text(encoding='utf-8')).get('entries', {})
        return {kind: row['anchor_sample'] for kind, row in entries.items()
                if kind in KINDS and isinstance(row.get('anchor_sample'), int)
                and not isinstance(row['anchor_sample'], bool) and row['anchor_sample'] >= 0}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {}
