"""PySceneDetect adapter. Returns cut times in seconds, relative to the first frame."""
from pathlib import Path

import scenedetect
from scenedetect import AdaptiveDetector, ContentDetector, ThresholdDetector, detect

VERSION = scenedetect.__version__


def _detector(mode: str, sensitivity: float, min_frames: int):
    # sensitivity is normalised: higher finds more cuts, so thresholds move down.
    if mode == "adaptive":
        return AdaptiveDetector(adaptive_threshold=5.5 - 5.0 * sensitivity, min_scene_len=min_frames)
    if mode == "content":
        return ContentDetector(threshold=50.0 - 45.0 * sensitivity, min_scene_len=min_frames)
    if mode == "threshold_fade":
        return ThresholdDetector(threshold=max(24.0 * sensitivity, 1.0), min_scene_len=min_frames)
    raise ValueError(f"Unsupported detection mode '{mode}'")


def detect_cut_times(path: Path, mode: str, sensitivity: float, min_frames: int) -> list[float]:
    scenes = detect(str(path), _detector(mode, sensitivity, min_frames), start_in_scene=True, backend="pyav")
    return [start.seconds for start, _ in scenes[1:]]
