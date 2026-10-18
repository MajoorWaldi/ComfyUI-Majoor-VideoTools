from fractions import Fraction
from pathlib import Path

import folder_paths
from comfy_api.latest import VideoComponents, VideoContainer, VideoFromComponents, io

from ..adapters.comfy_video import media_ref, preview_ref


class MajoorPreviewVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorPreviewVideo",
            display_name="Preview Video",
            category="Majoor/VideoTools",
            description="Preview a VIDEO, or an IMAGE batch, with optional audio. Nothing is saved to the output folder.",
            is_output_node=True,
            inputs=[
                io.Video.Input("video", optional=True, tooltip="A video to preview. Connect either video or images."),
                io.Image.Input("images", optional=True, tooltip="An image batch to preview as a video. Connect either video or images."),
                io.Audio.Input("audio", optional=True, tooltip="Audio played with the video. Replaces the video's own audio."),
                io.Float.Input("fps", default=24.0, min=1.0, max=240.0, step=0.001, tooltip="Frame rate of the images. Ignored with a video."),
            ],
            outputs=[],
        )

    @classmethod
    def execute(cls, video=None, images=None, audio=None, fps=24.0) -> io.NodeOutput:
        if (video is None) == (images is None):
            raise ValueError("Connect either video or images (not both, not neither). Audio alone cannot be previewed.")

        if video is not None and audio is None:
            return io.NodeOutput(ui={"majoor_preview": [preview_ref(video)]})

        if images is not None:
            components = VideoComponents(images=images, frame_rate=Fraction(fps).limit_denominator(1001), audio=audio)
        else:
            source = video.get_components()
            components = VideoComponents(images=source.images, frame_rate=source.frame_rate, audio=audio)

        temp = folder_paths.get_temp_directory()
        folder, name, counter, _, _ = folder_paths.get_save_image_path("MajoorPreview", temp, 0, 0)
        path = Path(folder) / f"{name}_{counter:05}_.mp4"
        VideoFromComponents(components).save_to(str(path), format=VideoContainer.MP4, codec="auto", preset="ultrafast")
        return io.NodeOutput(ui={"majoor_preview": [media_ref(path.resolve(), "temp", Path(temp).resolve())]})
