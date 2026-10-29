import numpy as np
from majoor_videotools.core.delivery_review import compare_boundaries


def test_real_boundaries_distinguish_a_flash_missing_cut_and_unexpected_change():
    frames = np.zeros((80, 12, 16), np.uint8)
    frames[24:] = 70
    frames[36] = 255
    frames[60:] = 140
    report = compare_boundaries(frames, [{'frame': 24, 'transition': 'cut'},
                                        {'frame': 36, 'transition': 'flash'},
                                        {'frame': 48, 'transition': 'cut'}], 24)
    assert [r['classification'] for r in report['boundaries']] == ['observed_cut', 'flash_or_accent', 'not_observed']
    assert report['unexpected_frames'] == [60]
    assert report['semantic_review'] == 'not_evaluated'


def test_a_slow_declared_transition_and_dark_static_scene_are_not_hard_failures():
    frames = np.zeros((50, 12, 16), np.uint8)
    frames[20:30] = np.arange(10, dtype=np.uint8)[:, None, None] * 10
    frames[30:] = 90
    report = compare_boundaries(frames, [{'frame': 24, 'transition': 'fade_black'}], 24)
    assert report['boundaries'][0]['classification'] == 'declared_transition'
    assert 'failed' not in report.values()
