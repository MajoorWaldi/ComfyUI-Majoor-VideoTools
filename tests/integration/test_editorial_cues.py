import pytest

from majoor_videotools.core.editorial_cues import arbitrate_cues
from majoor_videotools.core.motion_timing import shot_layers


def test_essential_action_wins_without_retiming():
    cues, report = arbitrate_cues([(1, 'impact')], [(1.1, 'click', 'action'), (1.05, 'whoosh', 'reveal'), (1.12, 'tick', 'decoration')], 4)
    assert cues == [(1.1, 'click')]
    assert len(report['dropped']) == 3


def test_reveal_precedes_narrative_and_decoration_independent_of_order():
    explicit = [(2, 'impact', 'decoration'), (2.1, 'pop', 'reveal')]
    first = arbitrate_cues([(2.05, 'whoosh')], explicit, 5)
    assert first[0] == [(2.1, 'pop')]
    assert first == arbitrate_cues([(2.05, 'whoosh')], explicit[::-1], 5)


def test_protected_gesture_excludes_decorations_but_allows_declared_action():
    cues, report = arbitrate_cues([(1, 'whoosh')], [(1.5, 'click', 'action'), (2, 'pop', 'decoration')], 4, protected=[(.5, 2.5)])
    assert cues == [(1.5, 'click')]
    assert {x['reason'] for x in report['dropped']} == {'protected_action'}


def test_quiet_edits_have_more_space_and_repeated_cues_are_limited():
    events = [(i * .5, 'hit') for i in range(12)]
    normal, _ = arbitrate_cues(events, [], 6)
    quiet, report = arbitrate_cues(events, [], 6, quiet=True)
    assert len(quiet) < len(normal)
    assert all(b[0] - a[0] >= 1.6 for a, b in zip(quiet, quiet[1:]))
    assert report['quiet']


def test_collision_policy_bounds_stacked_sounds_and_rejects_invalid_metadata():
    cues, _ = arbitrate_cues([], [(1, k, 'decoration') for k in ('impact', 'whoosh', 'tick', 'pop')], 3)
    assert cues == [(1, 'impact')]
    for at, kind, role in [(float('nan'), 'hit', 'action'), (3, 'hit', 'action'), (1, 'invented', 'action'), (1, 'hit', 'invented')]:
        with pytest.raises(ValueError):
            arbitrate_cues([], [(at, kind, role)], 3)
    with pytest.raises(ValueError, match='event_role'):
        shot_layers('[{"type":"box","event_role":"invented"}]', '[]', 3, 24)


def test_resolved_onset_survives_arbitration_exactly():
    rows, _ = shot_layers('[{"type":"box","start":0.3,"end":1.5,"sync":"onset","sfx":"hit","event_role":"reveal"}]', '[]', 2, 24, [.32])
    cues, _ = arbitrate_cues([], [(rows[0]['start'], 'hit', rows[0]['event_role'])], 2)
    assert cues == [(8 / 24, 'hit')]
