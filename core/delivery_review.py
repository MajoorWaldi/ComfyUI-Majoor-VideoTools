"""Advisory verification of the encoded picture. No semantic or identity verdict."""
import json
import os
import tempfile
from pathlib import Path
import numpy as np
from .fingerprints import file_fingerprint


def compare_boundaries(frames, expected, fps):
    changes = np.zeros(len(frames))
    for i in range(1, len(frames)):
        changes[i] = np.abs(frames[i].astype(np.float32) - frames[i-1]).mean()
    candidates = set(np.flatnonzero(changes >= 20).tolist())
    flashes = set()
    for i in sorted(candidates):
        if i + 1 < len(frames) and i + 1 in candidates:
            if np.abs(frames[i-1].astype(np.float32)-frames[i+1]).mean() < 8:
                flashes.update((i, i+1))
    rows, covered = [], set()
    for item in expected:
        at = int(item['frame'])
        near = {i for i in candidates if abs(i-at) <= 1}
        transition = item.get('transition', 'cut')
        if transition not in ('cut', 'hit', ''):
            label = 'flash_or_accent' if near & flashes else 'declared_transition'
            covered.update(i for i in candidates if abs(i-at) <= max(6, int(item.get('transition_frames', 0))))
        else:
            label = 'flash_or_accent' if near & flashes else 'observed_cut' if near else 'not_observed'
            covered.update(near)
        rows.append({'frame': at, 'seconds': at/fps, 'classification': label,
                     'observed_frames': sorted(near)})
    return {'boundaries': rows, 'unexpected_frames': sorted(candidates-covered-flashes),
            'semantic_review': 'not_evaluated', 'status': 'advisory',
            'method': 'small decoded-frame differences; +/-1 frame, thresholds 20/8; not a calibrated scene detector'}


def timeline_path(video):
    return Path(str(video) + '.delivery.json')


def save_timeline(video, metadata):
    path=timeline_path(video)
    fd, temporary=tempfile.mkstemp(dir=path.parent,suffix='.json.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump({**metadata,'video_fingerprint':file_fingerprint(video)},stream,indent=2)
        os.replace(temporary,path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def review_delivery(video, timeline_source=None):
    from .energy import read_gray
    from .media_probe import probe
    metadata_path = timeline_path(timeline_source or video)
    if not metadata_path.is_file(): return {'status': 'not_evaluated', 'reason': 'no_assembly_timeline'}
    try:
        data = json.loads(metadata_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'status': 'not_evaluated', 'reason': 'invalid_assembly_timeline'}
    if not isinstance(data, dict) or data.get('version') not in (1, 2) or not isinstance(data.get('boundaries'), list):
        return {'status': 'not_evaluated', 'reason': 'unsupported_assembly_timeline'}
    if data.get('video_fingerprint') != file_fingerprint(timeline_source or video):
        return {'status': 'not_evaluated', 'reason': 'stale_assembly_timeline'}
    info = probe(video, with_packets=False)
    if float(info.duration) > 180 or float(info.fps) > 60:
        return {'status': 'not_evaluated', 'reason': 'review_budget'}
    frames = read_gray(video, info.fps)
    try:
        result = compare_boundaries(frames, data['boundaries'], float(info.fps))
    finally:
        if hasattr(frames, '_mmap'): frames._mmap.close()
    return {**result, 'version': 1, 'video_fingerprint': file_fingerprint(video),
            'expected_source': 'final_assembly_segments', 'audio_source': data.get('audio_source')}
