import pytest
from majoor_videotools.core.skills import user_message


@pytest.mark.parametrize('event', [
    'Catch the floating light once; end with it resting in the open hand.',
    'Light already held; the reflection in his eyes fades as his expression becomes sad.',
    'Light already held; transfer it once into an open glass jar.',
    'Jar already contains the light; arrive in a dark silent bedroom.',
    'Already inside the dark bedroom; release the light from the jar once.',
])
def test_selected_event_does_not_receive_the_whole_film(event):
    global_brief='GLOBAL_STORY_SENTINEL: catch light, eye reaction, jar transfer, bedroom arrival, release.'
    local='SHOT_003\n'+event
    text=user_message(global_brief,local,1,voice=True,dialogue='0-1 s: "Here."',shot_only=True)
    assert 'GLOBAL_STORY_SENTINEL' not in text
    assert local in text and 'CURRENT SHOT ONLY' in text
    assert '<Picture 1>' in text and '<Audio 1>' in text and '"Here."' in text


def test_brief_only_writer_and_other_skills_keep_their_brief():
    assert 'BRIEF\nA single local action' in user_message('A single local action',shot_only=True)
    assert 'BRIEF\nWhole story' in user_message('Whole story','local rhythm',shot_only=False)
