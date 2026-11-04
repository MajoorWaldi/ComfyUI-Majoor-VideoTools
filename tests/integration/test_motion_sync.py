"""The start of a generated take chosen so that its motion lands on the attacks of the music, and the cut plan that reads the music by sections."""
import numpy as np

from majoor_videotools.core import motion_sync
from majoor_videotools.core.music_cuts import music_cut_plan, section_pacing

FPS = 24


def _take(moves, frames=40):
    """Small gray frames, still except a jump of the picture at each frame of `moves`."""
    rng = np.random.default_rng(1)
    base = rng.integers(40, 200, (90, 160), dtype=np.uint8)
    out, current = [], base
    for i in range(frames):
        if i in moves:
            current = np.roll(current, 9, axis=1)
        out.append(current.copy())
    return np.stack(out)


def test_a_take_whose_moves_come_late_starts_where_they_meet_the_attacks():
    take = _take({8, 20})  # the take moves at frames 8 and 20; the music hits 0.25 s and 0.75 s into the shot (frames 6 and 18)
    slip, score, base = motion_sync.best_slip(take, FPS, [(0.25, 1.0), (0.75, 1.0)], needed=24)
    assert slip == 2 and score > base


def test_a_take_already_on_the_music_or_without_attacks_keeps_its_start():
    take = _take({6, 18})
    assert motion_sync.best_slip(take, FPS, [(0.25, 1.0), (0.75, 1.0)], needed=24)[0] == 0
    assert motion_sync.best_slip(take, FPS, [], needed=24) == (0, 0.0, 0.0)
    assert motion_sync.best_slip(_take(set()), FPS, [(0.25, 1.0)], needed=24)[0] == 0  # a still take has no motion to place


def test_a_take_never_starts_so_late_that_the_shot_runs_out_of_frames():
    take = _take({30}, frames=30)
    assert motion_sync.best_slip(take, FPS, [(0.1, 1.0)], needed=28)[0] <= 2


def _music(seconds, rate=8000, pulse=True, quiet_until=0.0):
    """A tone with a kick every half second when `pulse`, or kicks at irregular times; quieter before `quiet_until`."""
    t = np.arange(round(seconds * rate)) / rate
    wave = .03 * np.sin(2 * np.pi * 220 * t)
    hits = np.arange(.5, seconds, .5) if pulse else np.cumsum(np.random.default_rng(4).uniform(.2, 1.4, int(seconds)))
    for at in hits[hits < seconds]:
        i = round(at * rate)
        n = min(round(.05 * rate), len(wave) - i)
        wave[i:i + n] += .5 * np.sin(2 * np.pi * 80 * t[:n]) * np.exp(-t[:n] * 60)
    wave[:round(quiet_until * rate)] *= .2
    return wave, rate


def test_a_section_with_a_steady_pulse_is_cut_on_the_beat_and_a_free_one_by_phrases():
    steady, rate = _music(12)
    assert all(s["pacing"] == "beat" for s in section_pacing(steady, rate, 120, 12))
    free, rate = _music(12, pulse=False)
    assert all(s["pacing"] == "phrase" for s in section_pacing(free, rate, 120, 12))
    assert all(s["pacing"] == "phrase" for s in section_pacing(steady, rate, 0, 12))  # no tempo at all: phrases


def test_the_plan_opens_each_section_with_a_cut_and_says_what_every_shot_starts_on():
    samples, rate = _music(24, quiet_until=8)
    plan, info = music_cut_plan(samples, rate, duration=24, fps=FPS, mode="adaptive", variation=.5)
    starts = [round(s["start"] * FPS) for s in info["sections"][1:] if s["end"] - s["start"] >= 2]
    bounds = set(np.cumsum([s["duration_frames"] for s in plan["shots"]])[:-1].tolist())
    assert starts and set(starts) <= bounds
    notes = [s["notes"] for s in plan["shots"]]
    assert any("opens the" in n for n in notes) and all(("cut on the beat" in n) or ("cut by phrases" in n) for n in notes)
    assert {"tag", "start", "end", "pacing", "pulse"} <= info["sections"][0].keys()


def test_syncopations_appear_only_with_variation_and_only_on_the_beat():
    samples, rate = _music(40)
    offbeat = lambda variation: sum("offbeat" in s["notes"] for seed in range(6)
                                    for s in music_cut_plan(samples, rate, duration=40, fps=FPS, variation=variation, seed=seed)[0]["shots"])
    assert offbeat(0) == 0 and offbeat(1) > 0


def test_a_stored_take_starts_on_the_music_unless_its_words_are_sung(tmp_path):
    import json
    import subprocess
    from dataclasses import replace
    from majoor_videotools.core.beats import write_wav
    from majoor_videotools.core.paths import ProjectStore
    from majoor_videotools.core.revisions import MUSIC_FILE, apply_revision, make_metadata
    from majoor_videotools.core.template import create_template

    shots = create_template(json.dumps({"shots": [{"id": "dance", "duration": 1, "prompt": "He dances"}]}), tmp_path, fps=FPS, aspect_ratio="16:9",
                            resolution=64, profile="none", thumbnails=False, card_text=False)
    store = ProjectStore(tmp_path, shots.project_id)
    rate = 8000
    music = np.zeros(rate * 2)
    for at in (.25, .75):  # two kicks a quarter and three quarters of a second into the shot
        i = round(at * rate)
        music[i:i + 400] = .8 * np.sin(2 * np.pi * 80 * np.arange(400) / rate) * np.exp(-np.arange(400) / 80)
    store.resolve(MUSIC_FILE).parent.mkdir(parents=True, exist_ok=True)
    write_wav(store.resolve(MUSIC_FILE), music[:, None], rate)

    def take(name, frames):
        path = tmp_path / name
        proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "160x90", "-r", str(FPS), "-i", "-",
                                 "-c:v", "libx264", "-crf", "1", "-pix_fmt", "yuv420p", str(path)], stdin=subprocess.PIPE)
        proc.stdin.write(_take({9, 21}, frames=frames).tobytes())  # the take moves three frames after each kick
        proc.stdin.close()
        proc.wait()
        return path

    shot = shots.shots[0]
    aligned = apply_revision(shots, tmp_path, make_metadata(shots, shot, shot.active), take("a.mp4", 34), align_to_music=True)
    assert aligned.shots[0].active.source_start_seconds == 3 / FPS
    plain = apply_revision(aligned, tmp_path, make_metadata(aligned, aligned.shots[0], aligned.shots[0].active), take("b.mp4", 35))
    assert plain.shots[0].active.source_start_seconds == 0.0  # the option is off
    sung = replace(plain, shots=(replace(plain.shots[0], plan={**plain.shots[0].plan, "prompt": 'He dances\nLyrics sung in this shot, word for word: "go"'}),))
    store.resolve("manifest.json").write_text(json.dumps(sung.to_dict()), encoding="utf-8")
    kept = apply_revision(sung, tmp_path, make_metadata(sung, sung.shots[0], sung.shots[0].active), take("c.mp4", 36), align_to_music=True)
    assert kept.shots[0].active.source_start_seconds == 0.0  # the mouth follows the sound from the first frame


def test_a_steady_rhythmic_track_without_a_loud_peak_still_gets_bursts():
    samples, rate = _music(24)
    samples[round(3 * rate):round(3.2 * rate)] *= 4  # one loud moment must not make the rest of the track read as calm
    shots = [s["duration_frames"] for s in music_cut_plan(samples, rate, duration=24, fps=FPS, mode="adaptive", variation=1, seed=2)[0]["shots"]]
    assert min(shots) <= 6
