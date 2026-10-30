"""A measured, frame-based score shared by assembly sound and finishing graphics."""
import json
from pathlib import Path

from .fingerprints import file_fingerprint, json_fingerprint
from .motion_timing import shot_layers


def build_score(rows, timeline, duration, fps, hits=()):
    resolved, alignment = shot_layers(json.dumps(rows), json.dumps(timeline), duration, fps, hits)
    events = [{'id': f'attack-{frame:08d}', 'frame': frame, 'seconds': frame / fps, 'origin': 'measured_music'}
              for frame in sorted({round(float(t) * fps) for t in hits if 0 <= float(t) < duration})]
    by_frame = {e['frame']: e['id'] for e in events}
    for row in alignment:
        row['event_id'] = by_frame.get(round(row['start'] * fps)) if row.get('matched') else None
    return {'version': 1, 'fps': fps, 'duration': duration, 'input_layers': json_fingerprint(rows),
            'timeline': timeline, 'events': events, 'layers': resolved, 'alignment': alignment}


def write_score(store, video: Path, score):
    if score is None:
        store.resolve(store.rel(video) + '.score.json').unlink(missing_ok=True)
    else:
        store.write_json(store.rel(video) + '.score.json', {**score, 'video_fingerprint': file_fingerprint(video)})


def read_score(video: Path, rows, duration, fps):
    path = video.with_name(video.name + '.score.json')
    if not path.is_file() or path.stat().st_size > 2_000_000:
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if (data['version'] != 1 or data['video_fingerprint'] != file_fingerprint(video)
                or data['input_layers'] != json_fingerprint(rows)
                or abs(data['duration'] - duration) > 1 / fps or abs(data['fps'] - fps) > .001):
            return None
        return data
    except (OSError, KeyError, TypeError, ValueError):
        return None
