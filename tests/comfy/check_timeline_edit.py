"""Comfy API/schema, real-media and optional isolated-server timeline checks.

Run with the Comfy interpreter. --server http://127.0.0.1:8197 --output-root
must point to that server's output directory; never use the shared live server.
"""
import argparse
import asyncio
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import _boot
import folder_paths
import numpy as np
import torch

from MVT.core.beats import write_wav
from MVT.core.errors import ManifestError
from MVT.core.media_probe import probe
from MVT.core.paths import ProjectStore
from MVT.core.revisions import apply_revision, make_metadata
from MVT.core.template import create_template
from MVT.core.timeline_edit import initial_document
from MVT.nodes import timeline_edit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--fixture-json", type=Path)
    args = parser.parse_args()
    if args.server and not args.output_root:
        parser.error("--server requires its isolated --output-root")
    extension = asyncio.run(_boot.pack.comfy_entrypoint())
    nodes = asyncio.run(extension.get_node_list())
    assert sum(n.define_schema().node_id == "MajoorTimelineEdit" for n in nodes) == 1
    with tempfile.TemporaryDirectory(prefix="mjr-timeline-check-") as directory:
        root = (args.output_root or Path(directory)) / "MajoorVideoTools"
        folder_paths.get_output_directory = lambda: str(root.parent)
        timeline_edit.projects_root = lambda shot_list=None: root
        sl = create_template(json.dumps({"shots": [{"duration": 1, "prompt": "Red"}, {"duration": 1, "prompt": "Blue"}]}),
                             root, fps=24, aspect_ratio="1:1", resolution=128, thumbnails=False)
        for shot, color in zip(sl.shots, ["red", "blue"]):
            path = Path(directory) / f"{color}.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color={color}:s=128x128:r=24:d=3",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
            sl = apply_revision(sl, root, make_metadata(sl, shot, shot.active), path, generation_prompt=f"A {color} plate")
        music = {"sample_rate": 8000, "waveform": torch.from_numpy(
            (.2 * np.sin(2 * np.pi * 440 * np.arange(24000) / 8000)).astype(np.float32)).reshape(1, 1, -1)}
        first = timeline_edit.MajoorTimelineEdit.execute(sl, music=music)
        assert first.result[1] is music
        payload = first.ui["majoor_timeline"][0]
        assert len(payload["music"]["peaks"]) == 1024
        assert max(payload["music"]["peaks"]) == 1
        assert payload["music"]["duration"] == 3
        store = ProjectStore(root, sl.project_id)
        assert store.resolve(payload["music"]["file"]).is_file()
        document = initial_document(sl)
        document["clips"].reverse()
        document["clips"][0].update(in_frame=24, out_frame=48)
        document["clips"].append({**document["clips"][0], "id": "copy"})
        edited = timeline_edit.MajoorTimelineEdit.execute(sl, json.dumps(document), music)
        assert len(edited.result[0].shots) == 3
        assert edited.result[0].shots[0].active.generation_prompt == "A blue plate"
        assert timeline_edit.MajoorTimelineEdit.execute(sl).result[1] is None
        silence = {**music, "waveform": torch.zeros((1, 2, 100))}
        assert max(timeline_edit.music_preview(store, silence)["peaks"]) == 0
        mono = timeline_edit.music_preview(store, {**music, "waveform": torch.zeros((1, 1, 200))})
        stereo = timeline_edit.music_preview(store, silence)
        assert mono["file"] != stereo["file"]
        for bad in [{"sample_rate": 0, "waveform": music["waveform"]},
                    {**music, "waveform": torch.ones((2, 1, 100))},
                    {**music, "waveform": torch.full((1, 1, 1), float("nan"))}]:
            try:
                timeline_edit.music_preview(store, bad)
            except ManifestError:
                pass
            else:
                raise AssertionError("Invalid audio was accepted")
        if args.fixture_json:
            args.fixture_json.write_text(json.dumps(payload), encoding="utf-8")
        print("Timeline schema, real node execution, takes, audio passthrough, waveform/silence and invalid audio OK")
        if args.server:
            store.resolve("music").mkdir(exist_ok=True)
            write_wav(store.resolve("music/retained.wav"), music["waveform"][0].numpy().T, 8000)
            prompt = {
                "1": {"class_type": "MajoorLoadShotList", "inputs": {"project_id": sl.project_id}},
                "2": {"class_type": "MajoorLoadProjectMusic", "inputs": {"project_id": sl.project_id}},
                "3": {"class_type": "MajoorTimelineEdit", "inputs": {"shot_list": ["1", 0], "music": ["2", 0], "edit_json": json.dumps(document)}},
                "4": {"class_type": "MajoorShotAssemble", "inputs": {
                    "shot_list": ["3", 0], "music": ["3", 1], "assembly_mode": "original_order",
                    "missing_shot_policy": "error", "duration_policy": "use_generated_duration",
                    "fps_policy": "source", "audio_policy": "mute", "output_format": "mp4",
                    "video_codec": "h264", "output_name": "timeline_check", "music_fade": 0}},
            }
            for attempt in range(3):
                if attempt == 2:
                    del prompt["3"]["inputs"]["music"]
                    del prompt["4"]["inputs"]["music"]
                    del prompt["2"]
                request = urllib.request.Request(args.server + "/prompt",
                                                 json.dumps({"prompt": prompt}).encode(),
                                                 headers={"Content-Type": "application/json"})
                queued = json.load(urllib.request.urlopen(request, timeout=30))
                assert queued.get("prompt_id") and not queued.get("node_errors"), queued
                history = {}
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    history = json.load(urllib.request.urlopen(args.server + "/history/" + queued["prompt_id"], timeout=10))
                    if history:
                        break
                    time.sleep(.2)
                run = history[queued["prompt_id"]]
                assert run["status"]["status_str"] == "success", run["status"]
                preview = run["outputs"]["4"]["images"][0]
                output = args.output_root / preview["subfolder"] / preview["filename"]
                assert probe(output).frame_count == 72 and probe(output).has_audio == (attempt < 2)
                if attempt == 1:
                    cached = [m[1]["nodes"] for m in run["status"]["messages"] if m[0] == "execution_cached"]
                    assert cached and "3" in cached[0] and "4" in cached[0], cached
                elif attempt == 0:
                    live = run["outputs"]["3"]["majoor_timeline"][0]
                    assert live["document"] == document
            print("Isolated Comfy /prompt: 72-frame assembly with/without music, persisted edit and second-run graph cache OK")


if __name__ == "__main__":
    main()
