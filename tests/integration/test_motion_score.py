import json
from pathlib import Path

from majoor_videotools.core.motion_score import build_score, read_score, write_score
from majoor_videotools.core.paths import ProjectStore
from majoor_videotools.core.motion_scenes import sound_events


def test_graphic_and_sound_share_exact_event_frame():
    rows = [{'type': 'vector', 'shape': 'ring', 'shot_id': 'A', 'start': .3, 'end': 1.5, 'sync': 'onset', 'sfx': 'hit'}]
    timeline = [{'id': 'A', 'start': 0, 'duration': 2}]
    score = build_score(rows, timeline, 2, 24, [.32])
    assert score['alignment'][0]['event_id'] == 'attack-00000008'
    assert score['layers'][0]['start'] == 8 / 24
    assert sound_events(score['layers'], timeline, 2, 24) == [(8 / 24, 'hit')]


def test_stale_or_changed_score_is_not_reused(tmp_path):
    store = ProjectStore(tmp_path, 'p_12345678')
    video = store.resolve('exports/final.mp4')
    video.write_bytes(b'video fixture')
    rows = [{'type': 'box', 'start': 0, 'end': 1}]
    score = build_score(rows, [], 2, 24, [.3])
    write_score(store, video, score)
    assert read_score(video, rows, 2, 24)['version'] == 1
    assert read_score(video, [], 2, 24) is None
    assert read_score(video, rows, 3, 24) is None
    video.write_bytes(b'changed video fixture')
    assert read_score(video, rows, 2, 24) is None


def test_real_assembly_emits_a_score_bound_to_its_measured_music(tmp_path):
    import numpy as np
    from majoor_videotools.core.template import create_template
    from majoor_videotools.core.assembler import AssemblyOptions, assemble_shots
    from majoor_videotools.core.beats import write_wav
    root = tmp_path / 'projects'
    shots = create_template('{"shots":[{"id":"A","duration":2}]}', root, fps=24, aspect_ratio='16:9', resolution=160, thumbnails=False, card_text=False)
    samples = np.zeros(48000 * 2, dtype=np.float32)
    samples[24000:24480] = np.hanning(480) * .8
    music = tmp_path / 'master.wav'
    write_wav(music, np.stack([samples, samples], axis=1), 48000)
    rows = [{'type': 'vector', 'shape': 'dot', 'shot_id': 'A', 'start': .45, 'end': 1.5, 'sync': 'onset', 'sfx': 'hit'}]
    options = AssemblyOptions(missing_shot_policy='use_original', audio_policy='mute', music=music, auto_sfx=True, motion_layers=json.dumps(rows))
    result = assemble_shots(shots, root, options)
    score = read_score(result.path, rows, 2, 24)
    assert score is not None and score['events']
    assert score['alignment'][0]['event_id'] in {e['id'] for e in score['events']}
    again = assemble_shots(shots, root, options)
    assert again.reused and read_score(again.path, rows, 2, 24) is not None


def test_real_assembly_arbitrates_explicit_sounds_and_preserves_protected_action(tmp_path):
    import numpy as np
    from majoor_videotools.core.template import create_template
    from majoor_videotools.core.assembler import AssemblyOptions, assemble_shots
    from majoor_videotools.core.beats import write_wav
    root = tmp_path / 'projects'
    plan = {'shots': [
        {'id': 'A', 'duration': 2, 'story': {'protect_action': True}},
        {'id': 'B', 'duration': 2},
    ]}
    shots = create_template(json.dumps(plan), root, fps=24, aspect_ratio='16:9', resolution=160, thumbnails=False, card_text=False)
    samples = np.zeros(48000 * 4, dtype=np.float32)
    for at in (.5, 1, 2.5, 3):
        begin = round(at * 48000)
        samples[begin:begin+480] = np.hanning(480) * .8
    music = tmp_path / 'master.wav'
    write_wav(music, np.stack([samples, samples], axis=1), 48000)
    rows = [
        {'type': 'box', 'shot_id': 'A', 'start': .5, 'end': 1.5, 'sfx': 'click', 'event_role': 'action'},
        {'type': 'box', 'shot_id': 'A', 'start': 1, 'end': 1.5, 'sfx': 'sparkle'},
        {'type': 'box', 'shot_id': 'B', 'start': .5, 'end': 1.5, 'sfx': 'pop', 'event_role': 'reveal'},
        {'type': 'box', 'shot_id': 'B', 'start': .55, 'end': 1.5, 'sfx': 'tick'},
    ]
    result = assemble_shots(shots, root, AssemblyOptions(missing_shot_policy='use_original', audio_policy='mute', music=music, auto_sfx=True, motion_layers=json.dumps(rows)))
    score = read_score(result.path, rows, 4, 24)
    assert [(x['start'], x['sfx']) for x in score['sound_cues']['kept']] == [(.5, 'click'), (2.5, 'pop')]
    assert {x['reason'] for x in score['sound_cues']['dropped']} == {'protected_action', 'collision'}
    assert len(score['layers']) == 4  # Audio arbitration never removes the visual layer.
