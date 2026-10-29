"""Resolve shot-local graphics against final timing and measured audio attacks."""
import json
import math
from .motion_scenes import style_layer
from .motion_contract import validate_motion_rows


def _local_seconds(value, length):
    """Accept explicit seconds as well as numeric and shot-relative times."""
    text = str(value).strip()
    percent = text.endswith('%')
    number = float(text[:-1] if percent or text.endswith('s') else text)
    if not math.isfinite(number):
        raise ValueError('Motion timing must be finite')
    return number * length / 100 if percent else number


def shot_layers(text, timeline, duration, fps, hits=()):
    data = json.loads(text or '[]')
    rows = data.get('layers', []) if isinstance(data, dict) else data
    if not isinstance(rows, list) or len(rows) > 120:
        raise ValueError('Motion layers must contain at most 120 objects')
    validate_motion_rows(rows)
    windows = {}
    for shot in json.loads(timeline or '[]'):
        start, length = float(shot['start']), float(shot['duration'])
        sid = str(shot['id'])
        if sid in windows or not math.isfinite(start + length) or start < 0 or length <= 0 or start + length > duration + 1 / fps:
            raise ValueError('Invalid final motion timeline')
        windows[sid] = (start, min(duration, start + length))
    attacks = sorted({(float(t), round(float(t) * fps) / fps) for t in hits if math.isfinite(float(t)) and 0 <= float(t) < duration})
    resolved, alignment = [], []
    rows = [style_layer(row) if isinstance(row, dict) else row for row in rows]
    # Dependencies stay inside a named scene and a shot, independent of JSON order.
    ids = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError('Motion layers must be objects')
        if row.get('id'):
            key=(row.get('shot_id'),row.get('scene'),str(row['id']))
            if key in ids: raise ValueError('Duplicate motion layer id inside scene')
            ids[key]=i
    visiting, ready = set(), set()
    def schedule(i):
        if i in ready:return
        if i in visiting:raise ValueError('Motion scene dependency cycle')
        visiting.add(i)
        row=rows[i]
        if row.get('after'):
            if not row.get('scene'):raise ValueError('Motion after needs a named scene')
            key=(row.get('shot_id'),row.get('scene'),str(row['after']))
            if key not in ids:raise ValueError('Unknown motion scene dependency')
            previous=ids[key];schedule(previous)
            sid=row.get('shot_id')
            if sid is not None and str(sid) not in windows:raise ValueError('Unknown motion shot_id')
            low,high=windows[str(sid)] if sid is not None else (0.,duration)
            def local(value):
                return _local_seconds(value, high-low)
            parent=rows[previous]
            parent_end=local(parent.get('end',high-low))
            phase=row.get('after_phase','end')
            if phase not in ('end','entered'):raise ValueError('Motion after_phase must be end or entered')
            if phase=='entered':
                parent_end=local(parent.get('start',0))+float(parent.get('in_time',.25))
            delay=local(row.get('delay',0));length=local(row.get('duration',high-low-parent_end-delay))
            if delay<0 or length<=0:raise ValueError('Motion scene needs nonnegative delay and positive duration')
            row.update(start=parent_end+delay,end=parent_end+delay+length)
        visiting.remove(i);ready.add(i)
    for i in range(len(rows)):schedule(i)
    groups={}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError('Motion layers must be objects')
        row = dict(row)
        sid = row.pop('shot_id', None)
        if sid is not None and str(sid) not in windows:
            raise ValueError(f'Unknown motion shot_id {sid!r}')
        low, high = windows[str(sid)] if sid is not None else (0., duration)
        def seconds(value, default):
            if value in (None, ''):
                return default
            return _local_seconds(value, high - low)
        start = low + seconds(row.get('start'), 0)
        end = low + seconds(row.get('end'), high - low)
        if sid is not None and (start < low or end > high + 1 / fps or end <= start or start >= high):
            raise ValueError('Shot-local motion must stay inside its shot')
        if sid is None:
            start, end = max(0, min(start, duration)), max(0, min(end, duration))
            if start >= duration:
                continue
            if end <= start:
                end = min(duration, start + .2)
        start = max(low, round(start * fps) / fps)
        end = min(high, max(start + 1 / fps, round(end * fps) / fps))
        sync = row.pop('sync', 'none')
        if sync not in ('none', 'onset'):
            raise ValueError('Motion sync must be none or onset')
        before = start
        group=(sid,row.get('scene')) if row.get('scene') else None
        if group:
            groups.setdefault(group,[]).append((len(resolved),sync,low,high))
        if sync == 'onset' and not group:
            # A small correction only: no invented grid or movement into the next shot.
            candidates = [t for measured, t in attacks if low <= measured < high and low <= t < end - 1 / fps and abs(t - start) <= .15]
            if candidates:
                start = min(candidates, key=lambda t: (abs(t - start), t))
            alignment.append({'layer': index, 'shot_id': sid, 'requested': before, 'start': start,
                              'matched': bool(candidates)})
        row.update(start=start, end=end)
        for name in ('id','after','after_phase','delay','duration','design'):
            row.pop(name,None)
        resolved.append(row)
    for (sid,name),members in groups.items():
        if not any(sync=='onset' for _,sync,_,_ in members):continue
        start=min(resolved[i]['start'] for i,_,_,_ in members)
        end=max(resolved[i]['end'] for i,_,_,_ in members)
        low,high=members[0][2:]
        candidates=[t for measured,t in attacks if low<=measured<high and abs(t-start)<=.15 and start+(t-start)>=low and end+(t-start)<=high]
        delta=min(candidates,key=lambda t:abs(t-start))-start if candidates else 0
        for i,_,_,_ in members:
            resolved[i]['start']+=delta;resolved[i]['end']+=delta
        alignment.append({'scene':name,'shot_id':sid,'requested':start,'start':start+delta,'matched':bool(candidates)})
    return resolved, alignment


def preview_times(layers, cues, timeline, duration, fps):
    """Bounded representative frames, including entrances and settled titles."""
    anchors = []
    for row in layers + cues:
        start, end = float(row.get('start', 0)), float(row.get('end') or duration)
        anchors.extend([start + min(.08, (end - start) / 4), min(end - 1 / fps, start + float(row.get('in_time', .3)) + .05)])
    for shot in json.loads(timeline or '[]'):
        anchors.append(float(shot['start']) + float(shot['duration']) / 2)
    anchors += [min(.2, duration / 2), duration - 1 / fps]
    frames = sorted({min(round(duration * fps) - 1, max(0, round(t * fps))) for t in anchors})
    if len(frames) > 16:
        frames = [frames[round(i * (len(frames) - 1) / 15)] for i in range(16)]
    return [frame / fps for frame in frames]
