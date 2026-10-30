"""Reproducible six-second procedural benchmark, not a model or narrative approval."""
import argparse
import json
import subprocess
import sys
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType("majoor_videotools")
package.__path__ = [str(ROOT)]
sys.modules.setdefault("majoor_videotools", package)

from majoor_videotools.core.assembler import AssemblyOptions, assemble_shots
from majoor_videotools.core.beats import write_wav
from majoor_videotools.core.editorial_graph import compile_project
from majoor_videotools.core.export_transaction import atomic_json
from majoor_videotools.core.fingerprints import file_fingerprint
from majoor_videotools.core.media_probe import probe
from majoor_videotools.core.scene_detection import detect_scenes
from majoor_videotools.core.timeline_edit import compile_edit, initial_document


def tones(path):
    audio = np.frombuffer(subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"]), dtype="<f4")
    result = []
    for index in range(4):
        begin = int((index * 1.5 + .25) * 8000)
        window = audio[begin:begin + 8000]
        if len(window) != 8000:
            raise ValueError("Benchmark audio does not cover every occurrence")
        result.append(float(np.argmax(abs(np.fft.rfft(window))) * 8000 / len(window)))
    return result


def benchmark(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "procedural-source.mp4"
    inputs = []
    for color, frequency in (("red", 440), ("lime", 660), ("blue", 880)):
        inputs += ["-f", "lavfi", "-i", f"color={color}:s=128x96:r=24:d=2",
                   "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=48000:duration=2"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex",
                    "[0:v][2:v][4:v]concat=n=3:v=1:a=0[v];[1:a][3:a][5:a]concat=n=3:v=0:a=1[a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", str(source)], check=True)
    root = directory / "projects"
    shots = detect_scenes(source, root, "manual", .5, 1, cut_points="48,96", thumbnails=True)
    document = initial_document(shots)
    document["clips"] = [{**document["clips"][index], "id": f"occurrence_{occurrence}", "in_frame": 6, "out_frame": 42}
                         for occurrence, index in enumerate((2, 0, 1, 2))]
    graph = compile_project(shots, document)
    edited = compile_edit(shots, document)
    result = assemble_shots(edited, root, AssemblyOptions(audio_policy="shot_audio", effects=False, output_name="benchmark"))
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(result.path),
                                   "-vf", "scale=1:1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    colors = np.frombuffer(raw, np.uint8).reshape(-1, 3)
    labels = np.argmax(colors, axis=1)
    cuts = (np.flatnonzero(labels[1:] != labels[:-1]) + 1).tolist()
    expected_cuts = [36, 72, 108]
    errors = [abs(actual - expected) for actual, expected in zip(cuts, expected_cuts)] if len(cuts) == 3 else None
    expected_audio = [880, 440, 660, 880]
    measured = tones(result.path)
    music = directory / "procedural-music.wav"
    write_wav(music, (.1 * np.sin(2 * np.pi * 220 * np.arange(6 * 48000) / 48000)).astype(np.float32)[:, None], 48000)
    locked = assemble_shots(edited, root, AssemblyOptions(audio_policy="mute", music=music, music_fade=0,
                                                        effects=False, output_name="locked-music"))
    locked_tones = tones(locked.path)
    passed = (probe(result.path).frame_count == 144 and errors == [0, 0, 0]
              and [int(labels[index * 36 + 12]) for index in range(4)] == [2, 0, 1, 2]
              and all(abs(a - b) < 5 for a, b in zip(measured, expected_audio))
              and all(abs(value - 220) < 5 for value in locked_tones))
    report = {"version": 1, "status": "PASS" if passed else "FAIL", "scope": "procedural_editing_only",
              "rights": "locally generated mathematical colors and sine waves; no third-party media",
              "duration_seconds": result.duration_seconds, "frames": probe(result.path).frame_count,
              "expected_cut_frames": expected_cuts, "observed_cut_frames": cuts, "cut_error_frames": errors,
              "expected_take_tones_hz": expected_audio, "measured_take_tones_hz": measured,
              "locked_music_tones_hz": locked_tones, "graph_fingerprint": graph.fingerprint,
              "occurrence_fingerprints": [clip.fingerprint for clip in graph.clips],
              "source_sha256": file_fingerprint(source), "output_sha256": file_fingerprint(result.path),
              "output": str(result.path), "music_output": str(locked.path),
              "model_generation": "NOT RUN", "human_identity_continuity_text_music_review": "NOT RUN",
              "release_approval": False}
    atomic_json(directory / "benchmark.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    result = benchmark(arguments.output_dir)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
