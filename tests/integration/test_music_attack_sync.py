import numpy as np

from majoor_videotools.core.beats import align_grid_to_onsets


def test_cut_grid_follows_nearby_attacks_without_retiming_the_track():
    rate=24000;fps=30
    audio=np.zeros(rate*4,dtype=np.float32)
    expected=[16,29,46,59,76,89]
    for frame in expected:
        start=round(frame/fps*rate);n=480
        audio[start:start+n]+=np.random.default_rng(frame).normal(size=n)*np.exp(-np.arange(n)/80)
    grid=[15,30,45,60,75,90]
    refined=align_grid_to_onsets(grid,audio,rate,fps)
    assert max(abs(a-b) for a,b in zip(refined,expected))<=1
    assert sum(abs(a-b) for a,b in zip(refined,expected))<sum(abs(a-b) for a,b in zip(grid,expected))
    assert all(abs(a-b)<=2 for a,b in zip(refined,grid))
    assert all(a<b for a,b in zip(refined,refined[1:]))


def test_silence_keeps_existing_grid_and_distant_attacks_do_not_pull_cuts():
    audio=np.zeros(48000,dtype=np.float32)
    grid=[10,20,30]
    assert align_grid_to_onsets(grid,audio,24000,30)==grid
    audio[12000:12020]=1
    assert align_grid_to_onsets(grid,audio,24000,30)==grid


def test_dense_grid_stays_strictly_ordered():
    audio=np.zeros(24000,dtype=np.float32);audio[8000:8050]=1
    grid=list(range(7,14))
    refined=align_grid_to_onsets(grid,audio,24000,30)
    assert all(a<b for a,b in zip(refined,refined[1:]))
    assert len(refined)==len(grid)
