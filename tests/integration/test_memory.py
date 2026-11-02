"""Visual memory: the frame kept of each take, by character, and the one a later shot gets."""
from types import SimpleNamespace

import cv2
import numpy as np

from majoor_videotools.core.memory import memory_file, memory_key, recall, remember, sharpest_frame
from majoor_videotools.core.paths import ProjectStore

PROJECT = "p_0123456789ab"


def _video(path, sharp_at):
    """24 frames of noise that is smooth everywhere except at the frame `sharp_at`, where it is crisp."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 24, (64, 64))
    rng = np.random.default_rng(1)
    for i in range(24):
        picture = rng.integers(0, 255, (64, 64, 3)).astype(np.uint8)
        writer.write(picture if i == sharp_at else cv2.GaussianBlur(picture, (15, 15), 0))
    writer.release()


def _shot(shot_id, start, character=None):
    return SimpleNamespace(shot_id=shot_id, start_frame=start, plan={"cast": {"character_id": character, "name": character.split("_")[0].title()}} if character else {})


def test_the_sharpest_frame_of_the_middle_of_the_take_is_kept(tmp_path):
    _video(tmp_path / "take.avi", 12)
    frame = sharpest_frame(tmp_path / "take.avi")
    assert frame is not None and cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var() > 500
    assert sharpest_frame(tmp_path / "missing.avi") is None


def test_a_shot_gets_the_latest_earlier_frame_of_the_same_person_only(tmp_path):
    store = ProjectStore(tmp_path, PROJECT)
    _video(tmp_path / "take.avi", 12)
    shots = [_shot("SHOT_001", 0, "ghoul"), _shot("SHOT_002", 48, "witch"), _shot("SHOT_003", 96, "ghoul_2"), _shot("SHOT_004", 144, "ghoul_3"), _shot("SHOT_005", 192)]
    shot_list = SimpleNamespace(shots=shots)
    assert recall(store, shot_list, shots[0]) is None                       # the first shot of a character has no memory
    for shot in shots[:3]:
        assert remember(store, memory_key(shot.plan["cast"]), shot.shot_id, tmp_path / "take.avi")
    assert recall(store, shot_list, shots[2]).name == "SHOT_001.png"         # the same ghoul listed again as ghoul_2, not the witch's frame
    assert recall(store, shot_list, shots[3]).name == "SHOT_003.png"         # the latest earlier one
    assert recall(store, shot_list, shots[1]) is None                       # the witch has no earlier shot
    assert recall(store, shot_list, shots[4]) is None                       # no character
    assert str(recall(store, shot_list, shots[3])).replace("\\", "/").endswith("cache/memory/ghoul/SHOT_003.png")


def test_a_name_that_is_not_a_plain_id_keeps_nothing(tmp_path):
    store = ProjectStore(tmp_path, PROJECT)
    _video(tmp_path / "take.avi", 12)
    assert memory_file(store, "../escape", "SHOT_001") is None and memory_file(store, "ghoul", "a/b") is None
    assert remember(store, "../escape", "SHOT_001", tmp_path / "take.avi") is None


def test_the_memory_frame_keeps_the_middle_sharp_and_blurs_the_surroundings():
    from majoor_videotools.core.memory import identity_only
    frame = np.random.default_rng(3).integers(0, 255, (200, 120, 3)).astype(np.uint8)
    done = identity_only(frame)
    sharp = lambda part: cv2.Laplacian(cv2.cvtColor(part, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
    assert done.shape == frame.shape and sharp(done[80:120, 50:70]) > 0.5 * sharp(frame[80:120, 50:70])   # the character stays
    assert sharp(done[:20, :20]) < 0.1 * sharp(frame[:20, :20])                                          # the place around it does not


def test_the_same_name_with_or_without_accents_is_the_same_person():
    assert memory_key({"name": "Sorcière"}) == memory_key({"name": "Sorciere"}) == "sorciere"
    assert memory_key({"name": "  "}) is None and memory_key(None) is None
