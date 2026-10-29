from majoor_videotools.core.template import _shot_fx


def test_requested_micro_cut_is_not_stretched_to_a_half_beat():
    result=_shot_fx({'sub_cuts':[{'weight':3},{'weight':45}]},0,48,[0,12,24,36,48])
    assert [c['frames'] for c in result['sub_cuts']]==[3,45]


def test_energy_burst_keeps_its_short_cuts_and_total_duration():
    result=_shot_fx({'sub_cuts':[{'weight':3,'zoom':[2,2]},{'weight':3},{'weight':42}]},0,48,[0,12,24,36,48])
    assert [c['frames'] for c in result['sub_cuts']]==[3,3,42]
    assert result['sub_cuts'][0]['zoom']==[2,2]


def test_calm_hold_and_normal_beat_cuts_remain_unchanged():
    plain={'zoom':[1,1.1]}
    assert _shot_fx(plain,0,96,[0,12,24,36,48,60,72,84,96]) is plain
    result=_shot_fx({'sub_cuts':[{'weight':24},{'weight':24}]},0,48,[0,12,24,36,48])
    assert [c['frames'] for c in result['sub_cuts']]==[24,24]


def test_micro_burst_before_the_first_detected_beat_keeps_its_timing():
    result=_shot_fx({'sub_cuts':[{'weight':3},{'weight':3},{'weight':42}]},0,48,[10,22,34,46,58])
    assert [c['frames'] for c in result['sub_cuts']]==[3,3,42]
