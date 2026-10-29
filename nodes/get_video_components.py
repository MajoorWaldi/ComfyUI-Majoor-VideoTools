import torch
from comfy_api.latest import io

from ..adapters.comfy_video import ensure_video_supported, sample_video_components, video_has_audio
from ..core.errors import MajoorError
from ..core.frame_select import parse_frames


class MajoorGetVideoComponentsAdvanced(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorGetVideoComponentsAdvanced",
            display_name="Get Video Components Advanced",
            category="Majoor/VideoTools",
            description="Get video metadata and selected image frames. File-backed videos are sampled before the frame batch is allocated, with a 512 MiB memory budget.",
            inputs=[
                io.Video.Input("video"),
                io.String.Input(
                    "frames",
                    default="",
                    tooltip="Frames to output, in the order written: '0-10, 24, 30-90:5, -1'. A range is inclusive, ':n' is a step, negative numbers count from the end, '~8' keeps 8 frames spread evenly. Empty outputs every frame. Selected file frames are decoded before allocating the batch; output is limited to 512 MiB.",
                ),
                io.Boolean.Input("load_images", default=True, tooltip="Off: the video is not decoded, only the numbers are read (width, height, duration, fps, frame_count): images is an empty batch, audio and frame_indices are empty."),
            ],
            outputs=[
                io.Video.Output(display_name="video", tooltip="The input video, unchanged."),
                io.Int.Output(display_name="width", tooltip="Width in pixels, after any crop."),
                io.Int.Output(display_name="height", tooltip="Height in pixels, after any crop."),
                io.Float.Output(display_name="duration", tooltip="Length of the video in seconds, after any trim."),
                io.Float.Output(display_name="fps"),
                io.Int.Output(display_name="frame_count", tooltip="Number of frames of the video, not of the selection."),
                io.Image.Output(display_name="images", tooltip="The chosen frames as an IMAGE batch."),
                io.Audio.Output(display_name="audio", tooltip="The whole audio of the video, whatever the frames chosen."),
                io.String.Output(display_name="frame_indices", tooltip="Index of every frame in images, for example 0, 24, 48. The same text works in the frames of this node and of Load Video Advanced."),
                io.Boolean.Output(display_name="has_audio", tooltip="The video has an audio track (also read when load_images is off)."),
            ],
        )

    @classmethod
    def execute(cls, video, frames, load_images=True) -> io.NodeOutput:
        ensure_video_supported(video)
        width, height = video.get_dimensions()
        if not load_images:
            return io.NodeOutput(video, width, height, float(video.get_duration()), float(video.get_frame_rate()), video.get_frame_count(), torch.zeros((0, height, width, 3)), None, "", video_has_audio(video))
        images, audio, frame_rate, count = sample_video_components(video, frames)
        if count == 0:
            raise MajoorError("The video has no frame.")
        indices = parse_frames(frames, count) if frames.strip() else list(range(count))
        text = f"0-{count - 1}" if len(indices) == count and indices == list(range(count)) else ", ".join(map(str, indices))
        return io.NodeOutput(video, width, height, float(video.get_duration()), float(frame_rate), count, images, audio, text, audio is not None)
