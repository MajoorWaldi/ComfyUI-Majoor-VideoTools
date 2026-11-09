"""What to send to a partner (API) video node for one shot, from the same few settings whatever the model.

`build_request` is pure: media are opaque handles (the links of a graph under expansion), so it runs and is tested without ComfyUI.
It returns the class of the node, its inputs as the API prompt wants them (the dynamic combo `model` is flattened into `model.<name>` keys)
and the notes about what had to be left out (more pictures than the model takes)."""
from dataclasses import dataclass, field

from .errors import MajoorError
from .generators import load_generator

ASPECTS = ("16:9", "9:16", "1:1", "4:3", "3:4")
RESOLUTIONS = ("480p", "720p", "1080p")
LTX_SIZES = {("16:9", "720p"): "1280x720", ("9:16", "720p"): "720x1280", ("16:9", "1080p"): "1920x1080", ("9:16", "1080p"): "1080x1920"}


@dataclass
class Request:
    class_type: str
    inputs: dict
    notes: list[str] = field(default_factory=list)
    video_fps: float = 0.0  # the fps the model makes, when it is set by the request (0: the model decides)
    media: list[str] = field(default_factory=list)  # the inputs that are references (handles), the others are widget values


def _take(handles: list, cap: int | None, what: str, notes: list[str], title: str) -> list:
    handles = [h for h in handles if h is not None]
    if cap is not None and len(handles) > cap:
        notes.append(f"{title} takes {cap} reference {what}: the last {len(handles) - cap} are left out")
        return handles[:cap]
    return handles


def build_request(generator_id: str, *, prompt: str, seconds: float, aspect: str = "16:9", resolution: str = "720p", audio: bool = True, seed: int = 0,
                  images: list | None = None, videos: list | None = None, audios: list | None = None, fps: float = 24.0) -> Request:
    gen = load_generator(generator_id)
    if gen.source != "api":
        raise MajoorError(f"Generator '{generator_id}' is not an API model")
    if aspect not in ASPECTS or resolution not in RESOLUTIONS:
        raise MajoorError(f"aspect_ratio {aspect!r} or resolution {resolution!r} unknown. Available: {ASPECTS}, {RESOLUTIONS}")
    if not prompt.strip():
        raise MajoorError("The prompt of the shot is empty")
    secs = max(1, round(seconds))
    notes: list[str] = []
    images = _take(list(images or []), gen.limit("images"), "images", notes, gen.title)
    videos = _take(list(videos or []), gen.limit("videos"), "videos", notes, gen.title)
    audios = _take(list(audios or []), gen.limit("audios"), "audios", notes, gen.title)

    if gen.family == "seedance":
        if not images and not videos:
            raise MajoorError(f"{gen.title} reference mode needs at least one reference picture or video for the shot")
        inputs = {
            "model": gen.model, "model.prompt": prompt, "model.resolution": resolution, "model.ratio": aspect, "model.duration": secs,
            "model.generate_audio": audio, "model.task_type": "reference", "model.output_format": "mp4",
            "model.auto_downscale": True, "model.auto_upscale": False, "seed": seed, "watermark": False,
        }
        inputs.update({f"model.reference_images.image_{i}": h for i, h in enumerate(images, 1)})
        inputs.update({f"model.reference_videos.video_{i}": h for i, h in enumerate(videos, 1)})
        inputs.update({f"model.reference_audios.audio_{i}": h for i, h in enumerate(audios, 1)})
        return Request(gen.node, inputs, notes, media=[k for k in inputs if k.startswith("model.reference_")])

    if gen.family == "wan":
        if aspect not in ("16:9", "9:16", "1:1", "4:3", "3:4"):
            raise MajoorError(f"{gen.title} has no {aspect} format")
        inputs = {
            "model": gen.model, "model.prompt": prompt, "model.resolution": resolution.upper(), "model.ratio": aspect, "model.duration": str(secs),
            "model.audio": audio, "model.prompt_extend": True, "seed": seed, "watermark": False,
        }
        inputs.update({f"model.reference_images.image{i}": h for i, h in enumerate(images, 1)})
        inputs.update({f"model.reference_videos.video{i}": h for i, h in enumerate(videos, 1)})
        inputs.update({f"model.reference_audios.audio{i}": h for i, h in enumerate(audios, 1)})
        return Request(gen.node, inputs, notes, media=[k for k in inputs if k.startswith("model.reference_")])

    if gen.family == "ltx":
        size = LTX_SIZES.get((aspect, resolution))
        if size is None:
            raise MajoorError(f"{gen.title} makes 16:9 and 9:16 at 720p or 1080p only (asked {aspect} {resolution})")
        inputs = {"model": gen.model, "model.duration": str(secs), "model.resolution": size, "model.fps": str(int(round(fps))) if round(fps) in (24, 25, 50) else "24",
                  "model.generate_audio": audio, "prompt": prompt, "seed": seed}
        if images:
            inputs["image"] = images[0]  # LTX starts from a picture: the shot begins on the first reference
            return Request(gen.node, inputs, notes, float(inputs["model.fps"]), media=["image"])
        return Request("LtxApi25TextToVideo", inputs, notes, float(inputs["model.fps"]))

    raise MajoorError(f"Generator '{generator_id}' has no request builder for the family {gen.family!r}")
