import pytest
from majoor_videotools.core.yue2_music import music_style,music_score,WORDLESS
from majoor_videotools.core.vendor.yue2.abc_tools import parse_abc


def test_style_keeps_requested_voice_or_instrumental_without_forcing_vocalises():
    style,lyrics,quiet=music_style('Trap, vocal chops, saturated 808',144,'F# minor')
    assert '144 BPM' in style and 'F# minor' in style and lyrics==WORDLESS and not quiet
    for prompt in ['Quiet felt piano','Trap instrumental, no vocals','Piano intime, sans voix']:
        assert music_style(prompt)[1:]==('[Instrumental]',True)
    assert music_style('Modern pop',lyrics='[Chorus]\nMy supplied words')[1:] == ('[Chorus]\nMy supplied words',False)


def test_instrumental_transfer_preserves_note_timing_and_removes_vocal_notes():
    abc='X:1\nT:\nM:4/4\nL:1/16\nQ:1/4=120\nV: Vocal clef=treble name="Vocal Melody" snm="Vocal"\nV: Ins clef=treble name="Ins Melody" snm="Inst."\nK:C\n% chorus\nV: Vocal\n"C"C4D4E4F4|\nV: Ins\nz16|\n'
    converted,info=music_score(abc,True)
    old=parse_abc(abc);new=parse_abc(converted)
    assert new.voices['Ins'].notes==old.voices['Vocal'].notes
    assert not new.voices['Vocal'].notes and new.bpm==old.bpm
    assert info['vocal_pitch_onset_duration_preserved'] and info['meter_and_tempo_preserved']
    assert music_score(abc,False)==(abc,{'instrumental':False,'converted':False})


def test_bad_instrumental_plan_fails_clearly_instead_of_silent_model_fallback():
    with pytest.raises(Exception,match='YuE2'):
        music_score('not a score',True)


def test_token_limited_final_pair_is_discarded_without_changing_valid_music():
    header='X:1\nT:\nM:4/4\nL:1/16\nQ:1/4=120\nV: Vocal clef=treble name="Vocal Melody" snm="Vocal"\nV: Ins clef=treble name="Ins Melody" snm="Inst."\nK:C\n'
    pair='V: Vocal\n"C"z16|\nV: Ins\nC4D4E4F4|\n'
    good=header+pair*79
    broken=good+'V: Vocal\n"C"z16|\nV: Ins\nC4D4E'
    expected,_=music_score(good,True)
    with pytest.warns(RuntimeWarning,match='incomplete final voice pair'):
        actual,info=music_score(broken,True)
    assert actual==expected
    assert info['discarded_incomplete_final_group']
    assert info['meter_and_tempo_preserved']


def test_truncation_recovery_refuses_damage_in_the_middle_or_no_valid_pair():
    header='X:1\nT:\nM:4/4\nL:1/16\nQ:1/4=120\nV: Vocal clef=treble name="Vocal Melody" snm="Vocal"\nV: Ins clef=treble name="Ins Melody" snm="Inst."\nK:C\n'
    pair='V: Vocal\n"C"z16|\nV: Ins\nC4D4E4F4|\n'
    cut='V: Vocal\n"C"z16|\nV: Ins\nC4D4E'
    for broken in [header+cut,header+pair+cut+'\n'+pair,header+pair.replace('C4D4E4F4|','C4D4|')+cut]:
        with pytest.raises(Exception,match='YuE2 instrumental score preparation failed'):
            music_score(broken,True)
