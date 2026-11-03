"""Edit Skills sends the frame of each shot to the LLM and says which shot each frame is.

Run with the ComfyUI Python interpreter:
    python custom_nodes/ComfyUI-Majoor-VideoTools/tests/comfy/check_edit_skills_shot_frames.py
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

import torch

import _boot  # noqa: F401
from MVT.core.scene_detection import detect_scenes
from MVT.nodes import edit_skills
from MVT.nodes.edit_skills import MajoorEditSkills


def main():
    root = Path(tempfile.mkdtemp())
    try:
        video = root / "two.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=2", "-pix_fmt", "yuv420p", str(video)], check=True)
        shots = detect_scenes(video, root / "projects", "manual", .5, 1, cut_points="24", thumbnails=True)
        pictures = torch.zeros(2, 64, 64, 3)
        args = dict(skill="remix_planner", overlays_splits=False, text_overlays=False, reference_mode=True, genre="all", duration=0, fps=0, aspect_ratio="auto",
                    n_pictures=1, text_allowed="", brief="b", extra_instructions="", profile="none", cut_density="auto", transition_intensity="auto",
                    creative_freedom="auto", reference_fidelity="auto", narrative_coherence="auto", rhythm_text="SHOTS", images=pictures)
        result = MajoorEditSkills.execute(**args, shot_list=shots)
        out = result.args if hasattr(result, "args") else result
        assert out[3].shape[0] == 4, out[3].shape  # two pictures, then one frame per shot
        assert "image 3 = SHOT_001\nimage 4 = SHOT_002" in out[1] and "<Picture 1> <Picture 2>" in out[1]
        plain = MajoorEditSkills.execute(**args)
        plain = plain.args if hasattr(plain, "args") else plain
        assert plain[3].shape[0] == 2 and "SHOT FRAMES" not in plain[1]

        original = edit_skills.MAX_SHOT_FRAMES
        edit_skills.MAX_SHOT_FRAMES = 2
        try:
            many = detect_scenes(video, root / "projects", "manual", .5, 1, cut_points="12, 24, 36", thumbnails=True)
            frames, ids = edit_skills._shot_frames(many)
            assert frames.shape[0] == 2 and ids == ["SHOT_001", "SHOT_004"]  # spread from the first shot to the last
        finally:
            edit_skills.MAX_SHOT_FRAMES = original
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
    print("ok   the planner gets the frame of every shot, numbered after the pictures")
