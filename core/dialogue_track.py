"""Independent take-audio excerpts shared by preview, manual edits and assembly."""
import json
import math
import os
import tempfile
import wave
from pathlib import Path

from ..adapters.ffmpeg import run_capture
from .errors import ManifestError
from .fingerprints import file_fingerprint, json_fingerprint
from .media_probe import probe
from .timeline_edit import DIALOGUE_KEY

KEY = DIALOGUE_KEY


def audio_duration(path):
    data = json.loads(run_capture(["-v", "error", "-select_streams", "a:0", "-show_entries",
                                   "stream=duration:format=duration", "-of", "json", str(path)], "ffprobe"))
    streams = data.get("streams", [])
    if not streams:
        raise ManifestError(f"Dialogue source has no audio: {path.name}")
    value = streams[0].get("duration")
    if value in (None, "N/A"):
        value = data.get("format", {}).get("duration")
    duration = float(value) if value is not None else 0
    if not math.isfinite(duration) or duration <= 0:
        raise ManifestError(f"Dialogue source has no valid audio duration: {path.name}")
    return duration


def audio_preview(store, relative):
    """Cached mono waveform and browser-decodable WAV; never modify a take."""
    path = store.resolve(relative)
    if not probe(path, with_packets=False).has_audio:
        return None
    digest = json_fingerprint([file_fingerprint(path), "dialogue-preview-v1"])[:24]
    target = store.resolve(f"cache/timeline/dialogue_{digest}.wav")
    metadata = target.with_suffix(".json")
    if target.is_file() and metadata.is_file():
        return store.read_json(store.rel(metadata))
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file():
        fd, name = tempfile.mkstemp(dir=target.parent, suffix=".wav")
        os.close(fd)
        try:
            run_capture(["-v", "error", "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
                         "-c:a", "pcm_s16le", name])
            os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)
    import array
    peaks = []
    with wave.open(str(target), "rb") as stream:
        count = stream.getnframes()
        bins = min(512, count)
        for i in range(bins):
            pcm = array.array("h")
            pcm.frombytes(stream.readframes((i + 1) * count // bins - i * count // bins))
            peaks.append(max(abs(v) for v in pcm) / 32768)
    result = {"file": store.rel(target), "peaks": peaks, "duration": count / 16000}
    store.write_json(store.rel(metadata), result)
    return result


def render_dialogue(store, entries, duration):
    """Render a positioned dialogue bus, refusing silent end truncation."""
    if not math.isfinite(duration) or duration <= 0 or not isinstance(entries, list) or len(entries) > 256:
        raise ManifestError("Dialogue rendering requires a positive video duration and at most 256 excerpts")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise ManifestError("Dialogue track: each excerpt needs a project media reference")
        if any(type(entry.get(k)) not in (int, float) or not math.isfinite(entry[k])
               for k in ("start", "duration", "at", "gain")):
            raise ManifestError("Dialogue track: timings and gain must be finite numbers")
        if entry["start"] < 0 or entry["at"] < 0 or entry["duration"] <= 0 or not 0 <= entry["gain"] <= 4:
            raise ManifestError("Dialogue track: invalid source window, position or gain")
        if entry["gain"] > 0 and entry["at"] + entry["duration"] > duration + 1e-6:
            raise ManifestError("Dialogue extends beyond the video. Extend the montage or explicitly trim/move the dialogue before exporting; it will not be cut automatically.")
        path = store.resolve(entry["file"])
        if entry["gain"] == 0:
            continue
        available = audio_duration(path)
        if entry["start"] + entry["duration"] > available + .05:
            raise ManifestError("Dialogue source window exceeds the available take audio")
    entries = [entry for entry in entries if entry["gain"] > 0]
    key = json_fingerprint(["dialogue-bus-v2", duration, entries,
                           [file_fingerprint(store.resolve(e["file"])) for e in entries]])[:24]
    target = store.resolve(f"cache/timeline/dialogue_bus_{key}.wav")
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    args, filters = ["-v", "error", "-nostdin", "-y"], []
    for i, entry in enumerate(entries):
        args += ["-ss", f"{entry['start']:.9f}", "-t", f"{entry['duration']:.9f}", "-i", str(store.resolve(entry["file"]))]
        delay = round(entry["at"] * 48000)
        filters.append(f"[{i}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS,volume={entry['gain']},adelay={delay}S:all=1[d{i}]")
    if entries:
        filters.append("".join(f"[d{i}]" for i in range(len(entries))) +
                       f"amix=inputs={len(entries)}:normalize=0,apad[out]")
    else:
        filters.append("anullsrc=r=48000:cl=stereo[out]")
    fd, filename = tempfile.mkstemp(dir=target.parent, suffix=".wav")
    os.close(fd)
    try:
        script = Path(filename).with_suffix(".txt")
        script.write_text(";\n".join(filters), encoding="utf-8")
        run_capture([*args, "-filter_complex_script", str(script), "-map", "[out]", "-t", f"{duration:.9f}",
                     "-c:a", "pcm_s16le", filename])
        if abs(audio_duration(Path(filename)) - duration) > 1 / 48000:
            raise ManifestError("Dialogue rendering produced an incomplete audio bus; export stopped")
        os.replace(filename, target)
    finally:
        Path(filename).unlink(missing_ok=True)
        Path(filename).with_suffix(".txt").unlink(missing_ok=True)
    return target
