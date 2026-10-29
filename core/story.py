"""Optional, compact continuity metadata carried through the existing planning call.

Warnings compare explicit declarations only: no extra model, pixel interpretation
or rejection of legacy/mood plans. A warning asks for review, never rewrites a shot.
"""
import re
from difflib import SequenceMatcher

FIELDS = ("role", "new_information", "start_state", "action", "end_state", "handoff")


def story_fields(value) -> dict:
    if not isinstance(value, dict):
        return {}
    result = {key: value[key].strip()[:500] for key in FIELDS
              if isinstance(value.get(key), str) and value[key].strip()}
    if value.get('protect_action') is True:
        result['protect_action'] = True
    return result


def _words(value):
    return re.findall(r'\w+', value.casefold())


def _near(left, right):
    a, b = _words(left), _words(right)
    if not a or not b:
        return False
    if a == b:
        return True
    # Short actions, negations and numbers carry too much meaning to approximate.
    guards = {'no', 'not', 'never', 'without', 'before', 'after', 'pas', 'sans', 'avant', 'apres'}
    if min(len(a), len(b)) < 8 or (set(a) & guards) != (set(b) & guards):
        return False
    if [x for x in a if any(c.isdigit() for c in x)] != [x for x in b if any(c.isdigit() for c in x)]:
        return False
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= .9


def story_issues(shots):
    issues = []
    previous = None
    for shot in shots:
        story = story_fields(shot.story)
        fields = ('new_information', 'start_state', 'action', 'end_state')
        repeated = bool(previous and all(story.get(k) and previous[1].get(k) and _near(story[k], previous[1][k]) for k in fields))
        deliberate_reset = story.get('role', '').casefold() in ('flashback', 'reprise', 'reset', 'loop', 'callback')
        if repeated and not deliberate_reset:
            issues.append(('story_repeat', f'{shot.shot_id}: same or nearly identical declared story event as {previous[0]}; check whether this shot adds useful information'))
        elif previous and not deliberate_reset:
            before = previous[1]
            start, old_start, old_end = (_words(x) for x in (story.get('start_state',''), before.get('start_state',''), before.get('end_state','')))
            if start and old_start and old_end and start == old_start and old_start != old_end:
                issues.append(('story_reset', f'{shot.shot_id}: declared start returns to the pre-action state of {previous[0]}; verify the prop state or explicitly justify a reset'))
            elif start and old_end and before.get('handoff') and not story.get('new_information') and not set(old_end).issubset(start) and not _near(before['end_state'], story['start_state']):
                issues.append(('story_handoff', f'{shot.shot_id}: declared start differs from the preceding end state without new_information explaining the change; review the handoff from {previous[0]}'))
        previous = (shot.shot_id, story)
    return issues


def story_warnings(shots) -> list[str]:
    return [message for _, message in story_issues(shots)]
