import numpy as np

from majoor_videotools.core.editorial_cues import arbitrate_cues
from majoor_videotools.core.tone_sfx import design_cues
from majoor_videotools.core.sfx import RATE, render_track


def test_preparation_and_impact_share_an_event_but_other_hits_still_collide():
    preparations = {}
    events = design_cues([(2., 'impact')], 8., preparations=preparations)
    kept, report = arbitrate_cues(events + [(2.1, 'hit')], [], 8., preparations=preparations)
    assert (2., 'riser') in kept and (2., 'impact') in kept
    assert (2.1, 'hit') not in kept
    assert report['preparations'][0]['landing'] == 2.


def test_explicit_sample_anchor_and_legacy_user_start():
    sound = np.zeros(4800, np.float32)
    sound[1200] = 1
    generated = render_track([(1., 'hit')], 2, {'hit': sound}, generated={'hit'}, anchors={'hit': 1200})
    assert np.argmax(abs(generated[:, 0])) == RATE
    user = render_track([(1., 'hit')], 2, {'hit': sound}, anchors={'hit': 1200})
    assert np.argmax(abs(user[:, 0])) == RATE + 1200


def test_style_palette_is_seeded_bounded_and_preserves_user_overrides():
    events = [(float(i), 'hit') for i in range(1, 8)]
    a = design_cues(events, 10, palette='metallic', seed=42)
    assert a == design_cues(events, 10, palette='metallic', seed=42)
    assert {kind for _,kind in a} <= {'metal_tick', 'metal_chime', 'hit'}
    assert len({kind for _,kind in a}) > 1
    assert design_cues(events, 10, {'hit'}, palette='metallic') == events


def test_bus_balance_is_advisory_and_does_not_claim_perceptual_loudness():
    from majoor_videotools.core.sfx import cue_balance
    rate=8000
    program=np.full(rate*3,.1)
    bus=np.zeros((rate*3,2));bus[rate:rate+3200]=.2
    report=cue_balance([(1,'impact'),(1,'riser')],bus,program,rate,rate)
    assert len(report)==1 and report[0]['kinds']==['impact','riser']
    assert 5 < report[0]['relative_rms_db'] < 7
    assert report[0]['scope']=='SFX versus music only; not LUFS or perceived audibility'
    assert cue_balance([(1,'hit')],bus,np.zeros(rate*3),rate,rate)[0]['relative_rms_db'] is None


def test_explicit_action_riser_is_not_demoted_by_an_automatic_pair():
    kept,_=arbitrate_cues([(2,'impact')],[(2,'riser','action')],4,
                         preparations={(2,'riser'):(2,'impact')})
    assert kept==[(2,'riser')]
