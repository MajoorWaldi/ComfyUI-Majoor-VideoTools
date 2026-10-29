import asyncio
import os
from pathlib import Path

import folder_paths
import torch
from aiohttp import web
from comfy_api.latest import InputImpl, VideoComponents, io

from ..core.errors import MajoorError
from ..core.frame_select import parse_frames
from ..core.media_probe import probe

# A selection of at most SPARSE_MAX frames from a clip whose decoded frames would need more than SPARSE_BYTES (float32 RGB) reads the frames one by one
SPARSE_BYTES = 512 * 1024**2
SPARSE_MAX = 64


def _path(file: str) -> Path:
    """The file of the combo, inside the input, output or temp folder (the value of a combo is untrusted once it names a file)."""
    try:
        path = Path(folder_paths.get_annotated_filepath(file)).resolve()
    except ValueError:
        raise MajoorError(f"Invalid video file: {file}") from None
    roots = [Path(d).resolve() for d in (folder_paths.get_input_directory(), folder_paths.get_output_directory(), folder_paths.get_temp_directory())]
    if not any(root in path.parents for root in roots) or not path.is_file():
        raise MajoorError(f"Invalid video file: {file}")
    return path


def _frame_pts(path: Path, video) -> tuple[list[int], object]:
    """The pts of the frames of the (trimmed) clip, and the time base of the stream: what the decoder keeps, counted from the packets without decoding."""
    info = probe(path)
    start, duration = video.get_active_trim_window()
    first = int(start / info.time_base)
    end = int((start + duration) / info.time_base) if duration else None
    return [p for p in info.pts if p >= first and (end is None or p < end)], info.time_base


def _read_frames(path: Path, pts: list[int], time_base, indices: list[int], crop: tuple[int, int, int, int]) -> torch.Tensor:
    """Only the frames at `indices`, each decoded from a window of one tick around its pts: the clip is never held whole."""
    cache: dict[int, torch.Tensor] = {}
    for i in dict.fromkeys(indices):
        window = InputImpl.VideoFromFile(str(path)).as_trimmed(float((pts[i] + 0.1) * time_base), float(1.05 * time_base), strict_duration=False).as_cropped(*crop)
        frames = window.get_components().images
        if frames.shape[0] != 1:
            raise MajoorError(f"Frame {i} could not be read on its own ({frames.shape[0]} frames in its window).")
        cache[i] = frames
    return torch.cat([cache[i] for i in indices])


class MajoorLoadVideoAdvanced(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        input_dir = folder_paths.get_input_directory()
        files = folder_paths.filter_files_content_types([f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))], ["video"])
        return io.Schema(
            node_id="MajoorLoadVideoAdvanced",
            display_name="Load Video Advanced",
            category="Majoor/VideoTools",
            description="Load a video, trim it in time, crop it, and keep only chosen frames.",
            inputs=[
                io.Combo.Input("file", options=sorted(files), upload=io.UploadType.video),
                io.Float.Input("start_time", default=0.0, min=-1e5, max=1e5, step=0.001, tooltip="Start in seconds. Negative counts from the end."),
                io.Float.Input("duration", default=0.0, min=0.0, max=1e5, step=0.001, tooltip="Length in seconds, 0 for up to the end."),
                io.Int.Input("crop_x", default=0, min=0, max=16384, tooltip="Left edge of the crop in pixels."),
                io.Int.Input("crop_y", default=0, min=0, max=16384, tooltip="Top edge of the crop in pixels."),
                io.Int.Input("crop_width", default=0, min=0, max=16384, tooltip="Crop width in pixels, rounded down to an even number. 0 (or crop_height 0) keeps the full frame. A crop that leaves the frame is cut at its edge."),
                io.Int.Input("crop_height", default=0, min=0, max=16384, tooltip="Crop height in pixels, rounded down to an even number."),
                io.String.Input(
                    "frames",
                    default="",
                    tooltip="Frames to keep, counted after trim and crop, in the order written: '0-10, 24, 30-90:5, -1'. "
                    "A range is inclusive, ':n' is a step, negative numbers count from the end, '~8' keeps 8 frames spread evenly. Empty keeps every frame. "
                    "With a selection the audio is dropped (unless it keeps every frame). Up to 64 frames of a long clip are read one by one, so the clip is never loaded whole.",
                ),
            ],
            outputs=[
                io.Video.Output(),
                io.Image.Output(display_name="images", tooltip="Every kept frame as an IMAGE batch."),
                io.Int.Output(display_name="frame_indices", is_output_list=True, tooltip="Index of every kept frame in the trimmed and cropped clip. A list: a node connected to it runs once per index."),
            ],
        )

    @classmethod
    def execute(cls, file, start_time, duration, crop_x, crop_y, crop_width, crop_height, frames) -> io.NodeOutput:
        path = _path(file)
        video = InputImpl.VideoFromFile(str(path))
        if start_time or duration:
            video = video.as_trimmed(start_time, duration, strict_duration=False)
        video = video.as_cropped(crop_x, crop_y, crop_width, crop_height)

        if frames.strip():
            info = probe(path, with_packets=False)
            if info.frame_count * info.width * info.height * 12 > SPARSE_BYTES:
                pts, time_base = _frame_pts(path, video)
                indices = parse_frames(frames, len(pts))
                if 0 < len(indices) <= SPARSE_MAX:
                    images = _read_frames(path, pts, time_base, indices, (crop_x, crop_y, crop_width, crop_height))
                    return io.NodeOutput(InputImpl.VideoFromComponents(VideoComponents(images=images, frame_rate=video.get_frame_rate(), audio=None)), images, indices)

        source = video.get_components()
        images = source.images
        if images.shape[0] == 0:
            raise MajoorError("The clip has no frame: start_time is after the end of the video, or the video is empty.")
        indices = list(range(images.shape[0]))
        if frames.strip():
            indices = parse_frames(frames, images.shape[0])
            if not indices:
                raise MajoorError("frames selects no frame.")
            if indices != list(range(images.shape[0])):  # every frame in order keeps the video and its audio
                images = images[indices]
                video = InputImpl.VideoFromComponents(VideoComponents(images=images, frame_rate=source.frame_rate, audio=None))
        return io.NodeOutput(video, images, indices)

    @classmethod
    def fingerprint_inputs(cls, file, **kwargs):
        return os.path.getmtime(_path(file))

    @classmethod
    def validate_inputs(cls, file, **kwargs):
        try:
            _path(file)
        except MajoorError as e:
            return str(e)
        return True


def register_routes() -> None:
    from server import PromptServer

    @PromptServer.instance.routes.get("/majoor/video_info")
    async def video_info(request):
        try:
            info = await asyncio.to_thread(probe, _path(request.query.get("file", "")), False)
        except MajoorError as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"width": info.display_size[0], "height": info.display_size[1], "fps": float(info.fps), "duration": float(info.duration), "frames": info.frame_count})
