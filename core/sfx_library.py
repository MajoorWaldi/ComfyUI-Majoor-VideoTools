"""Optional local, attributed WAV cues. No downloads or bundled third-party audio."""
import hashlib
import json
import wave
from pathlib import Path

import numpy as np

from .errors import MajoorError
from .tone_sfx import KINDS


def load_library(directory: str) -> tuple[dict[str,np.ndarray],str]:
    if not directory.strip():return {},'procedural-v1'
    root=Path(directory).resolve()
    try:
        manifest=(root/'manifest.json').read_bytes()
        entries=json.loads(manifest)
        if not isinstance(entries,dict):raise ValueError('manifest must be an object')
        sounds={};digest=hashlib.sha256(manifest)
        for kind,item in entries.items():
            if kind not in KINDS:raise ValueError(f'Unknown cue {kind}')
            if not isinstance(item,dict) or not all(isinstance(item.get(k),str) and item[k].strip() for k in ('file','license','source')):
                raise ValueError(f'{kind}: file, license and source are required')
            path=(root/item['file']).resolve()
            if not path.is_relative_to(root) or path.suffix.lower()!='.wav':raise ValueError('Cue must be a WAV inside the library')
            payload=path.read_bytes();digest.update(payload)
            with wave.open(str(path),'rb') as audio:
                if audio.getsampwidth()!=2 or audio.getnchannels() not in (1,2):raise ValueError('Use 16-bit mono/stereo PCM WAV cues')
                rate=audio.getframerate()
                samples=np.frombuffer(audio.readframes(audio.getnframes()),dtype='<i2').astype(np.float32)/32768
                channels=audio.getnchannels()
                if channels==2:samples=samples.reshape(-1,2)
            if not len(samples):raise ValueError('Empty cue')
            count=round(len(samples)*48000/rate)
            positions=np.arange(count)*rate/48000
            sounds[kind]=(np.stack([np.interp(positions,np.arange(len(samples)),samples[:,c]) for c in range(2)],axis=1) if channels==2 else np.interp(positions,np.arange(len(samples)),samples)).astype(np.float32)
        return sounds,digest.hexdigest()
    except (OSError,ValueError,KeyError,TypeError,wave.Error) as error:
        raise MajoorError(f'Invalid local SFX library: {error}') from error
