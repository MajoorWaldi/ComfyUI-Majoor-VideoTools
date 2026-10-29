"""Model-free dialogue workflow checks. Use only a dedicated isolated Comfy server."""
import argparse
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import _boot
import numpy as np

from MVT.core.dialogue_track import render_dialogue
from MVT.core.media_probe import probe
from MVT.core.paths import ProjectStore
from MVT.core.revisions import apply_revision, make_metadata
from MVT.core.template import create_template
from MVT.core.timeline_edit import initial_document


def request(server, path, body=None):
    with urllib.request.urlopen(urllib.request.Request(server + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"}), timeout=30) as response:
        return json.load(response)


def execute(server, graph, succeeds=True):
    queued = request(server, "/prompt", {"prompt": graph})
    assert queued.get("prompt_id") and not queued.get("node_errors"), queued
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        history = request(server, "/history/" + queued["prompt_id"]).get(queued["prompt_id"])
        if history:
            assert (history["status"]["status_str"] == "success") is succeeds, history["status"]
            return history
        time.sleep(.2)
    raise AssertionError("Dialogue workflow timed out")


def samples(path):
    return np.frombuffer(subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path),
                         "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"]), dtype=np.float32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    schema = request(args.server, "/object_info/MajoorShotAssemble")["MajoorShotAssemble"]["input"]["optional"]
    assert "dialogue" in schema and schema["preserve_dialogue"][1]["default"] is False
    root = args.output_root / "MajoorVideoTools"
    with tempfile.TemporaryDirectory(prefix="dialogue-takes-") as directory:
        sl = create_template(json.dumps({"shots": [{"duration": 1, "prompt": color} for color in ("red", "blue", "green")]}),
                             root, fps=24, aspect_ratio="1:1", resolution=64, thumbnails=False)
        for shot, color in zip(sl.shots, ("red", "blue", "green")):
            path = Path(directory) / f"{color}.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color={color}:s=64x64:r=24:d=4",
                            "-f", "lavfi", "-i", "aevalsrc=0.2*sin(2*PI*(330*t+90*t*t)):s=48000:d=4",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
            sl = apply_revision(sl, root, make_metadata(sl, shot, shot.active), path)
        store = ProjectStore(root, sl.project_id)
        manifest = store.resolve("manifest.json").read_bytes()
        document = initial_document(sl)
        document["clips"].reverse()
        document["dialogue"] = [{**document["clips"][0], "id": "voice", "in_frame": 6, "out_frame": 66, "at_frame": 6, "gain": .5}]
        graph = {
            "1": {"class_type": "MajoorLoadShotList", "inputs": {"project_id": sl.project_id}},
            "2": {"class_type": "MajoorTimelineEdit", "inputs": {"shot_list": ["1", 0], "edit_json": json.dumps(document)}},
            "3": {"class_type": "MajoorShotAssemble", "inputs": {
                "shot_list": ["2", 0], "assembly_mode": "original_order", "missing_shot_policy": "error",
                "duration_policy": "trim_or_error", "fps_policy": "source", "audio_policy": "shot_audio",
                "output_format": "mp4", "video_codec": "h264", "output_name": "dialogue_check"}},
        }
        first = execute(args.server, graph)
        preview = first["outputs"]["3"]["images"][0]
        output = args.output_root / preview["subfolder"] / preview["filename"]
        assert probe(output).frame_count == 72
        data = samples(output)
        for second in (.5, .95, 1.05, 1.5, 1.95, 2.05, 2.5):
            part = data[round((second - .04) * 48000):round((second + .04) * 48000)]
            frequency = np.argmax(abs(np.fft.rfft(part * np.hanning(len(part))))) * 48000 / len(part)
            assert abs(frequency - (330 + 180 * second)) < 14, (second, frequency)
        payload = first["outputs"]["2"]["majoor_timeline"][0]
        assert payload["document"] == document
        take = payload["library"][0]["takes"][0]
        assert take["audio"] and len(take["audio"]["peaks"]) == 512
        second = execute(args.server, graph)
        assert any(m[0] == "execution_cached" and "3" in m[1]["nodes"] for m in second["status"]["messages"])
        assert store.resolve("manifest.json").read_bytes() == manifest
        bus = render_dialogue(store, [{"file": sl.shots[0].active.media_ref, "start": .25, "duration": 2.5, "at": .25, "gain": .5}], 3.)
        shutil.copyfile(bus, args.input_root / "dialogue-check.wav")
        graph["4"] = {"class_type": "LoadAudio", "inputs": {"audio": "dialogue-check.wav"}}
        graph["3"]["inputs"].update(shot_list=["1", 0], dialogue=["4", 0], effects=False, sub_cuts=False)
        del graph["2"]
        explicit = execute(args.server, graph)
        preview = explicit["outputs"]["3"]["images"][0]
        explicit_data = samples(args.output_root / preview["subfolder"] / preview["filename"])
        assert np.sqrt(np.mean(explicit_data[1000:8000] ** 2)) < .001
        graph["3"]["inputs"].pop("dialogue")
        graph["3"]["inputs"].update(voice_shots=True, preserve_dialogue=True)
        del graph["4"]
        failed = execute(args.server, graph, succeeds=False)
        assert any(m[0] == "execution_error" and "beyond the video" in m[1].get("exception_message", "")
                   for m in failed["status"]["messages"])
        graph["3"]["inputs"]["duration_policy"] = "use_generated_duration"
        full = execute(args.server, graph)
        preview = full["outputs"]["3"]["images"][0]
        assert probe(args.output_root / preview["subfolder"] / preview["filename"]).frame_count == 288
        assert store.resolve("manifest.json").read_bytes() == manifest
    print("Real Comfy API: 72-frame J/L cuts, continuous chirp across 2 cuts, dialogue waveform/document, graph cache, AUDIO input, safe overflow refusal, 288-frame full voice assembly and unchanged takes OK")


if __name__ == "__main__":
    main()
