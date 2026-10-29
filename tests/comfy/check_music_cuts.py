"""Model-free rhythm workflow checks against an isolated ComfyUI server."""
import argparse
import json
import time
import urllib.request
from pathlib import Path

import _boot
import numpy as np

from MVT.core.beats import write_wav
from MVT.core.media_probe import probe
from MVT.core.models import ShotList
from MVT.core.revisions import apply_revision, make_metadata


def request(server, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(server + path, data=data,
            headers={"Content-Type": "application/json"}), timeout=20) as response:
        return json.load(response)


def execute(server, graph):
    queued = request(server, "/prompt", {"prompt": graph})
    assert not queued.get("node_errors"), queued
    prompt_id = queued["prompt_id"]
    for _ in range(300):
        history = request(server, f"/history/{prompt_id}").get(prompt_id)
        if history:
            assert history["status"]["status_str"] == "success", history["status"]
            return history
        time.sleep(.2)
    raise AssertionError("Music rhythm workflow did not finish")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--input-root", type=Path, required=True, help="Isolated server input directory")
    parser.add_argument("--output-root", type=Path, required=True, help="Isolated server output directory")
    args = parser.parse_args()
    schema = request(args.server, "/object_info/MajoorCreateTimeline")["MajoorCreateTimeline"]
    assert schema["input"]["optional"]["music_edit_mode"][1]["default"] == "legacy"
    rate = 8000
    t = np.arange(rate * 9) / rate
    samples = .05 * np.sin(2 * np.pi * 220 * t)
    for seconds in np.arange(.5, 9, .5):
        at = round(seconds * rate)
        samples[at:at + 400] += .5 * np.sin(2 * np.pi * 80 * t[:400]) * np.exp(-t[:400] * 60)
    path = args.input_root.resolve() / "music-cuts-check.wav"
    write_wav(path, samples.reshape(-1, 1), rate)
    source = json.dumps({"shots": [
        {"id": "red", "duration": 3, "prompt": "Red city"},
        {"id": "blue", "duration": 3, "prompt": "Blue water"},
        {"id": "green", "duration": 3, "prompt": "Green field"},
    ]})
    for mode in ("adaptive", "random", "regular", "free", "legacy"):
        graph = {
            "1": {"class_type": "LoadAudio", "inputs": {"audio": path.name}},
            "2": {"class_type": "MajoorCreateTimeline", "inputs": {
                "source": "json", "source.plan_json": source, "source.cut_snap": "off",
                "source.duration": 9., "source.bpm": 0., "fps": 24., "aspect_ratio": "1:1",
                "resolution": 64, "generation_profile": "none", "music": ["1", 0],
                "preview_thumbnails": False, "card_text": False,
                "music_edit_mode": mode, "music_cut_density": "high", "music_cut_variation": .7,
                "music_cut_sync": .8, "music_cut_seed": 1337, "music_cut_every": "beat",
            }},
        }
        first = execute(args.server, graph)
        payload = first["outputs"]["2"]["majoor_shots"][0]
        assert [row["id"] for row in payload["shots"]] == ["red", "blue", "green"]
        assert sum(row["frames"] for row in payload["shots"]) == 216
        project = args.output_root.resolve() / Path(payload["base"])
        manifest_path = project / "manifest.json"
        before = manifest_path.read_bytes()
        manifest = json.loads(before)
        assert probe(project / manifest["source"]["uri"]).frame_count == 216
        actual = [c["frames"] for row in manifest["shots"]
                  for c in row.get("plan", {}).get("fx", {}).get("sub_cuts", [{"frames": row["end_frame_exclusive"] - row["start_frame"]}])]
        assert sum(actual) == 216
        second = execute(args.server, graph)
        assert any(message[0] == "execution_cached" and "2" in message[1]["nodes"]
                   for message in second["status"]["messages"]), second["status"]
        assert before == manifest_path.read_bytes()
        print(f"{mode}: real workflow, {len(payload['shots'])} takes, {len(actual)} edit segments, 216 frames, cache reused")
    sl = ShotList.from_dict(manifest)
    root = args.output_root.resolve() / "MajoorVideoTools"
    for shot in sl.shots:
        sl = apply_revision(sl, root, make_metadata(sl, shot, shot.active), project / sl.source.uri)
    before = manifest_path.read_bytes()
    graph = {
        "1": {"class_type": "LoadAudio", "inputs": {"audio": path.name}},
        "2": {"class_type": "MajoorLoadShotList", "inputs": {"project_id": sl.project_id}},
        "3": {"class_type": "MajoorShotAssemble", "inputs": {
            "shot_list": ["2", 0], "music": ["1", 0],
            "assembly_mode": "original_order", "missing_shot_policy": "error",
            "duration_policy": "trim_or_pad_last_frame", "fps_policy": "source",
            "audio_policy": "mute", "output_format": "mp4", "video_codec": "h264",
            "output_name": "remix_adaptive_check", "music_edit_mode": "adaptive",
            "music_cut_density": "high", "music_cut_variation": .5, "music_cut_sync": .8,
            "music_cut_seed": 1337, "effects": True, "sub_cuts": True,
        }},
    }
    assembled = execute(args.server, graph)
    output = assembled["outputs"]["3"]
    preview = output["images"][0]
    rendered = args.output_root.resolve() / Path(preview["subfolder"]) / preview["filename"]
    assert probe(rendered).frame_count == 216
    assert len(output["majoor_assembly"][0]["shots"]) == 3
    assert any("Musical Remix" in warning for warning in output["majoor_assembly"][0]["warnings"])
    assert manifest_path.read_bytes() == before
    second = execute(args.server, graph)
    assert any(message[0] == "execution_cached" and "3" in message[1]["nodes"]
               for message in second["status"]["messages"])
    print("Remix adaptive: real Shot Assemble export, 3 takes, 216 frames, generation manifest untouched, cache reused")
    print("All five music rhythm policies passed on the isolated ComfyUI server")


if __name__ == "__main__":
    main()
