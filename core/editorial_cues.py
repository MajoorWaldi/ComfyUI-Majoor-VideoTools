"""Bound editorial accents without moving their declared visual timestamps."""
import math

ROLES = {'action': 4, 'reveal': 3, 'narrative': 2, 'decoration': 1}


def arbitrate_cues(automatic, explicit, seconds, *, protected=(), quiet=False, preparations=None):
    """One accent per window; priorities express intent, never inferred physical sound.

    Explicit entries are (seconds, kind, event_role). All times are already resolved.
    User audio files and the underlying music are outside this editorial bus.
    """
    from .sfx import GAINS, PRIORITY
    explicit = list(explicit)
    explicit_keys = {(float(t), k) for t, k, _ in explicit}
    preparations = {key: parent for key, parent in (preparations or {}).items() if key not in explicit_keys}
    candidates = {}
    for at, kind, role in [*( (t, k, 'narrative') for t, k in automatic), *explicit]:
        if role not in ROLES or kind not in GAINS:
            raise ValueError('Unknown editorial cue role or sound')
        at = float(at)
        if not math.isfinite(at) or not 0 <= at < seconds:
            raise ValueError('Editorial cue must be inside the edit')
        key = (at, kind)
        if key not in candidates or ROLES[role] > ROLES[candidates[key]]:
            candidates[key] = role
    for key, parent in preparations.items():
        if key in candidates and parent in candidates:
            candidates[key] = candidates[parent]
    gap, repeat_gap, limit = (.8, 1.6, 2) if quiet else (.4, .8, 4)
    kept, dropped = [], []
    ranked = sorted(candidates.items(), key=lambda x: (-ROLES[x[1]], -PRIORITY[x[0][1]], x[0][0], x[0][1]))
    for (at, kind), role in ranked:
        reason = None
        parent = preparations.get((at, kind))
        paired = parent is not None and any((t, k) == parent for t, k, _ in kept)
        if role != 'action' and any(start <= at < end for start, end in protected):
            reason = 'protected_action'
        elif parent is not None and not paired:
            reason = 'missing_landing'
        elif any(abs(at - t) < gap - 1e-8 and (not paired or (t, k) != parent) for t, k, _ in kept):
            reason = 'collision'
        elif any(k == kind and abs(at - t) < repeat_gap - 1e-8 for t, k, _ in kept):
            reason = 'repetition'
        else:
            times = sorted([*([at] if not paired else []), *(t for t, k, _ in kept if (t,k) not in preparations)])
            if any(sum(t <= x < t + 2 for x in times) > limit for t in times):
                reason = 'density'
        if reason:
            dropped.append({'start': at, 'sfx': kind, 'event_role': role, 'reason': reason})
        else:
            kept.append((at, kind, role))
    kept.sort()
    return [(t, k) for t, k, _ in kept], {
        'quiet': quiet, 'minimum_gap': gap, 'repeat_gap': repeat_gap,
        'preparations': [{'start': t, 'sfx': k, 'landing': preparations[(t,k)][0]}
                         for t, k, _ in kept if (t,k) in preparations],
        'kept': [{'start': t, 'sfx': k, 'event_role': r} for t, k, r in kept],
        'dropped': sorted(dropped, key=lambda x: (x['start'], x['sfx'])),
    }
