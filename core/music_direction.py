"""Strict musical direction shared by native nodes; no model or network dependency."""
import json
import re

from .errors import MajoorError

ENERGIES=('calm','balanced','intense')


def parse_direction(text:str,user_mood:str='',bpm:int=0)->dict:
    raw=text.strip()
    if raw.startswith('```'):
        raw='\n'.join(raw.splitlines()[1:-1])
    try:
        start=raw.find('{')
        data=json.JSONDecoder().raw_decode(raw[start:] if start>=0 else raw)[0]
    except (ValueError,TypeError) as error:raise MajoorError('The music director did not return valid JSON') from error
    if isinstance(data,dict):data={str(k).strip().lower():v for k,v in data.items()}
    if not isinstance(data,dict) or not isinstance(data.get('prompt'),str) or not data['prompt'].strip():
        raise MajoorError('Music direction needs a nonempty prompt')
    energy=data.get('energy','balanced')
    if energy not in ENERGIES:raise MajoorError('Music energy must be calm, balanced or intense')
    tempo=bpm or data.get('bpm',120)
    if isinstance(tempo,bool) or not isinstance(tempo,(int,float)) or not 60<=tempo<=200:
        raise MajoorError('Music tempo must be between60and200BPM')
    prompt=(user_mood.strip()+', ' if user_mood.strip() else '')+data['prompt'].strip()
    key=data.get('key','C major')
    if isinstance(key,str):
        match=re.search(r'\b([A-Ga-g])([#b♭♯]?)\s*[-_ ]*\s*(major|minor|maj|min)\b',key,re.I)
        if match:
            root=match[1].upper()+match[2].replace('♭','b').replace('♯','#')
            root={'Cb':'B','E#':'F','Fb':'E','B#':'C'}.get(root,root)
            scale='major' if match[3].lower().startswith('maj') else 'minor'
            key=f'{root} {scale}'
    keys={f'{root} {scale}' for root in ('C','C#','Db','D','D#','Eb','E','F','F#','Gb','G','G#','Ab','A','A#','Bb','B') for scale in ('major','minor')}
    if key not in keys:raise MajoorError(f'Music direction has an invalid key: {key!r}')
    moments=data.get('moments',[])
    if not isinstance(moments,list) or any(not isinstance(m,dict) for m in moments):raise MajoorError('Music moments must be a list of objects')
    moments=[{str(k).strip().lower():v for k,v in m.items()} for m in moments]
    return {'prompt':prompt,'bpm':round(tempo),'energy':energy,'key':key,
            'moments':moments,'reason':str(data.get('reason',''))}
