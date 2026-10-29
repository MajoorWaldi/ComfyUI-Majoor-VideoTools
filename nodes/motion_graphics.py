import hashlib
import json
from pathlib import Path

import numpy as np
from filelock import FileLock

import comfy.model_management
import comfy.utils
from comfy_api.latest import VideoFromFile, io

from ..adapters.comfy_video import projects_root, video_file
from ..core.fingerprints import file_fingerprint
from ..core.media_probe import probe
from ..core.motion import ANIMATIONS, TYPES, needs_mask, parse_layers, render_motion

CODE_VERSION = "3-hyperframes"
WEB = Path(__file__).resolve().parents[1] / "web"


class MajoorMotionGraphics(io.ComfyNode):
    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return file_fingerprint(WEB / "hyperframes_scene.html") + file_fingerprint(WEB / "hyperframes_layers.js")

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorMotionGraphics",
            display_name="Motion Graphics",
            category="Majoor/VideoTools",
            description="Draw animated texts, boxes, corner brackets, emojis, glitch / chromatic aberration / grid / dots effects, an outline around the subject and points that track something over a video, from a JSON list of layers. "
                        "Uses the shared local HyperFrames runtime; the original audio is retained.",
            inputs=[
                io.Video.Input("video"),
                io.String.Input("layers", default='[{"type": "text", "content": "TITLE", "position": "top_left", "size": 0.08, "color": "white", "start": 0.5, "animation": "typewriter", "out": "fade"}]', multiline=True,
                                tooltip=f"A list of layers, or {{\"layers\": [...]}}. type: {', '.join(TYPES)}. animation: {', '.join(ANIMATIONS)}. start / end: seconds or a percentage of the video (\"40%\"). "
                                        "text: content, position (center, top, bottom, left, right, top_left...) or x / y, size (of the height), color, background, stroke, rotate. box and brackets: rect [x, y, width, height] as fractions of the frame, color, thickness. "
                                        "outline (needs the mask), effect (kind chromatic, glitch, grid, dots, scanlines; target frame, subject, background), track (anchor subject_top... or at [x, y]; label, emoji, shape, line). "
                                        "Every layer: opacity, in_time (seconds of the animation), out (fade). An empty list gives the video back as it is."),
                io.Mask.Input("mask", optional=True, lazy=True, tooltip="The subject, one mask per frame (any segmentation node). Needed by outline, by the effects aimed at the subject or the background and by the points anchored on the subject."),
                io.String.Input("output_name", default="motion", tooltip="Name of the file written to output/MajoorVideoTools/motion/ (a hash of the video and of the layers is added: an identical request reuses the file)."),
            ],
            outputs=[io.Video.Output(display_name="video"), io.String.Output(display_name="info", tooltip="The layers as they were read (times in seconds, values brought into range).")],
        )

    @classmethod
    def check_lazy_status(cls, layers='[]', mask=None, **kwargs):
        return ['mask'] if mask is None and needs_mask(parse_layers(layers, 1.0)) else []

    @classmethod
    def execute(cls, video, layers, output_name, mask=None) -> io.NodeOutput:
        with video_file(video) as path:
            info = probe(path, with_packets=False)
            parsed = parse_layers(layers, float(info.duration))
            summary = json.dumps(parsed, indent=1)
            if not parsed:
                return io.NodeOutput(video, summary)
            masks = mask.cpu().numpy() if mask is not None and needs_mask(parsed) else None
            key = hashlib.sha256(json.dumps([CODE_VERSION, cls.fingerprint_inputs(), path.stat().st_size, path.stat().st_mtime_ns, parsed, None if masks is None else [masks.shape, hashlib.sha256(np.ascontiguousarray(masks).tobytes()).hexdigest()]], sort_keys=True).encode()).hexdigest()[:10]
            name = "".join(c for c in output_name if c.isalnum() or c in "-_") or "motion"
            out = projects_root() / "motion" / f"{name}_{key}.mp4"
            out.parent.mkdir(parents=True,exist_ok=True)
            with FileLock(str(out)+'.lock',timeout=120):
                if not out.exists():
                    bar = comfy.utils.ProgressBar(1000)
                    fallback = render_motion(path, parsed, out, on_progress=lambda f: bar.update_absolute(int(f * 1000), 1000), is_cancelled=comfy.model_management.processing_interrupted, masks=masks)
                    if fallback:
                        out.unlink(missing_ok=True)
                else:
                    fallback = None
        warning_details = fallback.get("warning_details", []) if fallback else []
        ui = {"text": (warning_details[0]["message"],), "hyperkut_optional_warnings": warning_details} if warning_details else None
        return io.NodeOutput(video if fallback else VideoFromFile(str(out)), summary, ui=ui)
