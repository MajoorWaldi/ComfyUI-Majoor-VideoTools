from majoor_videotools.core.skills import compose, load_skill, module_states
from majoor_videotools.core.profiles import profile_text


def test_planned_vector_geometry_uses_normalized_units():
    skill = load_skill('timeline_planner')
    text, _ = compose(skill, module_states(skill))
    assert 'never pixel counts' in text
    assert 'fine lines 0.002' in text


def test_continuity_does_not_freeze_the_location():
    text = profile_text('none', narrative_coherence='high')
    assert 'space and time stay consistent' not in text
    assert 'Preserve fixed identity and setting' not in text
    assert 'motivated changes of location' in text


def test_h3_dialogue_keeps_official_voice_relationship_and_verbatim_content():
    for name in ('h3_shot_prompt_from_plan', 'remix_shot_prompt'):
        skill = load_skill(name)
        text, _ = compose(skill, module_states(skill, dialogue=True))
        assert '<d>[Language]' in text and '(S1)' in text
        assert '<Audio 1>: reference -' in text
        assert '<Audio 1>: attribute_transfer' not in text
        assert 'first frame' in text.lower()
        without, _ = compose(skill, module_states(skill, dialogue=False))
        assert '<d>[Language]' not in without


def test_creative_modules_are_local_and_selected_only_when_relevant():
    from majoor_videotools.core.skills import user_message
    plain=user_message('GLOBAL: anamorphic sad performance','A static red bottle',0,shot_only=True)
    assert 'LOCAL OPTICS' not in plain and 'LOCAL PERFORMANCE' not in plain
    emotional=user_message('', 'He hesitates, then looks toward the doorway.',1,shot_only=True)
    assert 'LOCAL PERFORMANCE' in emotional and 'LOCAL OPTICS' not in emotional
    optical=user_message('', 'An anamorphic close-up, the rear lamp creates bokeh.',1,shot_only=True)
    assert 'LOCAL OPTICS' in optical
    assert len(optical.split()) < 160
