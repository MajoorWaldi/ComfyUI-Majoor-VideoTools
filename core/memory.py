"""Visual memory: one frame of each take that was kept, filed by character, so that a later shot of the same character can start from how it really looked.

The frames live in the project's `cache/memory` folder, derived from the takes: deleting them only means later shots get no memory."""
import re
import unicodedata
from pathlib import Path

import cv2
import numpy as np

from .paths import ProjectStore

SAMPLES = 9  # frames looked at between a fifth and four fifths of the take; the sharpest one is kept
NAME = re.compile(r"[A-Za-z0-9_-]+")


def sharpest_frame(path):
    """The sharpest of a few frames from the middle of the video, as a BGR image, or None when the video cannot be read."""
    capture = cv2.VideoCapture(str(path))
    try:
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        best, best_score = None, -1.0
        for index in np.unique(np.linspace(total * .2, total * .8, SAMPLES).astype(int)) if total > 0 else ():
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if ok and (score := cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()) > best_score:
                best, best_score = frame, score
        return best
    finally:
        capture.release()


def identity_only(frame):
    """The frame with its surroundings blurred away: the character stays sharp in the middle, the place and the pose around it are not an instruction for the next shot.

    The sharp part is an ellipse in the middle of the picture with soft edges: generated shots keep their character centred."""
    height, width = frame.shape[:2]
    mask = np.zeros((height, width), np.float32)
    cv2.ellipse(mask, (width // 2, height // 2), (int(width * .30), int(height * .46)), 0, 0, 360, 1.0, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), min(width, height) * .06)[..., None]
    blurred = cv2.GaussianBlur(frame, (0, 0), min(width, height) * .05)
    return (frame * mask + blurred * (1 - mask)).astype(np.uint8)


def memory_key(cast: dict | None) -> str | None:
    """Who a shot shows, for the memory: the name of its character, since a character the casting lists again later (ghoul, ghoul_2) is the same person."""
    name = (cast or {}).get("name") or (cast or {}).get("character_id") or ""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()  # Sorcière and Sorciere are the same person
    return re.sub(r"[^a-z0-9]+", "_", plain.lower()).strip("_") or None


def memory_file(store: ProjectStore, character_id: str, shot_id: str) -> Path | None:
    """Where the memory frame of a shot is filed, or None for a name that is not a plain id."""
    if not NAME.fullmatch(character_id) or not NAME.fullmatch(shot_id):
        return None
    return store.resolve(f"cache/memory/{character_id}/{shot_id}.png")


def remember(store: ProjectStore, character_id: str, shot_id: str, video) -> Path | None:
    """Keep a frame of the take as the memory of this shot (replacing the one of an earlier take). None when there is nothing to keep."""
    target = memory_file(store, character_id, shot_id)
    frame = sharpest_frame(video) if target else None
    if frame is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target), identity_only(frame))
    return target


def recall(store: ProjectStore, shot_list, shot) -> Path | None:
    """The memory frame of the latest earlier shot of the same character, or None: the first shot of a character has none."""
    character = memory_key((shot.plan or {}).get("cast"))
    if not character:
        return None
    earlier = [s for s in shot_list.shots if s.start_frame < shot.start_frame and memory_key((s.plan or {}).get("cast")) == character]
    for other in sorted(earlier, key=lambda s: s.start_frame, reverse=True):
        path = memory_file(store, character, other.shot_id)
        if path is not None and path.is_file():
            return path
    return None
