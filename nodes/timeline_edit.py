"""Comfy bridge for the non-destructive timeline editor."""
import hashlib
import os
import tempfile
from pathlib import Path

import numpy as np
from comfy_api.latest import io

from ..adapters.comfy_video import MajoorShotList, OUTPUT_SUBFOLDER, projects_root
from ..core.beats import write_wav
from ..core.errors import ManifestError
from ..core.paths import ProjectStore
from ..core.timeline_edit import compile_edit, dialogue_bounds, initial_document, parse_document, take_bounds
from ..core.dialogue_track import audio_preview


def music_preview(store: ProjectStore, music) -> dict | None:
    if music is None:
        return None
    wave, rate = music["waveform"], music["sample_rate"]
    if type(rate) is not int or rate <= 0:
        raise ManifestError("Timeline Edit: audio sample_rate must be a positive integer")
    if wave.ndim != 3 or wave.shape[0] != 1 or wave.shape[1] not in (1, 2) or wave.shape[2] < 1:
        raise ManifestError("Timeline Edit: music must be one mono/stereo AUDIO batch [1,C,T]")
    samples = wave.detach().cpu().float().numpy()[0].T
    if not np.isfinite(samples).all():
        raise ManifestError("Timeline Edit: music contains non-finite samples")
    pcm = np.ascontiguousarray((np.clip(samples, -1, 1) * 32767).astype("<i2"))
    hasher = hashlib.sha256(f"{rate}:{pcm.shape[1]}:pcm16".encode())
    hasher.update(memoryview(pcm))
    digest = hasher.hexdigest()[:24]
    rel = f"cache/timeline/music_{digest}.wav"
    path = store.resolve(rel)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".wav")
        os.close(fd)
        try:
            write_wav(Path(tmp), samples, rate)
            os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)
    # Measure exactly the quantized samples played by the browser.
    peak = np.max(np.abs(pcm.astype(np.float32)), axis=1)
    edges = np.linspace(0, len(peak), min(1024, len(peak)) + 1, dtype=int)
    peaks = np.array([peak[a:b].max() for a, b in zip(edges[:-1], edges[1:])])
    scale = float(peaks.max())
    return {"file": rel, "duration": len(samples) / rate,
            "peaks": (peaks / scale).tolist() if scale else [0.] * len(peaks)}


def editor_payload(shot_list, store: ProjectStore, music) -> dict:
    library = []
    audio_cache = {}
    for shot in sorted(shot_list.shots, key=lambda s: s.timeline_index):
        takes = []
        for revision in shot.revisions:
            if shot_list.source.template and revision.media_range is not None:
                continue
            offset, frames = take_bounds(shot_list, shot, revision)
            if not store.resolve(revision.media_ref).is_file():
                raise FileNotFoundError(f"{shot.shot_id}/{revision.revision_id}: {revision.media_ref} is missing")
            if revision.media_ref not in audio_cache:
                audio_cache[revision.media_ref] = audio_preview(store, revision.media_ref)
            audio = audio_cache[revision.media_ref]
            if audio is not None:
                audio = {**audio, "frames": dialogue_bounds(shot_list, shot, revision)[1]}
            takes.append({"id": revision.revision_id, "file": revision.media_ref,
                          "offset": float(offset), "frames": frames, "prompt": revision.generation_prompt,
                          "audio": audio})
        library.append({"id": shot.shot_id, "takes": takes})
    return {"base": f"{OUTPUT_SUBFOLDER}/{shot_list.project_id}", "library": library,
            "initial": initial_document(shot_list), "music": music_preview(store, music)}


class MajoorTimelineEdit(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorTimelineEdit", display_name="Timeline Edit",
            category="Majoor/VideoTools",
            description="Non-destructive raw-take video editing with an independent dialogue track. Run once to load the editor; edit, then run to assemble. "
                        "Does not regenerate media or reapply automatic plan effects. Music is fixed at zero and passed through unchanged.",
            inputs=[MajoorShotList.Input("shot_list"),
                    io.String.Input("edit_json", default="", multiline=True,
                                    tooltip="Saved edit document. Empty initializes from the connected shot list. Use the editor to change it."),
                    io.Audio.Input("music", optional=True)],
            outputs=[MajoorShotList.Output(display_name="shot_list"), io.Audio.Output(display_name="music")],
        )

    @classmethod
    def execute(cls, shot_list, edit_json="", music=None) -> io.NodeOutput:
        document = parse_document(shot_list, edit_json)
        result = compile_edit(shot_list, document)
        payload = editor_payload(shot_list, ProjectStore(projects_root(), shot_list.project_id), music)
        payload["document"] = document
        return io.NodeOutput(result, music, ui={"majoor_timeline": [payload]})
