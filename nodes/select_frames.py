from comfy_api.latest import io

from ..core.frame_select import every_n_frames, retime_frames


class MajoorSelectEveryNFrames(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorSelectEveryNFrames",
            display_name="Select Every N Frames",
            category="Majoor/VideoTools",
            description="Keep one frame out of every N of an IMAGE batch, for a model that reads a few pictures (an LLM). spread_to_end keeps the last frame and thins the frames evenly so that max_frames of them cover the clip from the first to the last.",
            inputs=[
                io.Image.Input("images"),
                io.Int.Input("every_n", default=8, min=1, max=100000, tooltip="Frame 0, N, 2N... are kept."),
                io.Int.Input("max_frames", default=16, min=0, max=4096, tooltip="0: no limit. Otherwise at most this many frames."),
                io.Boolean.Input("spread_to_end", default=True, tooltip="On: the last frame is always kept, and when more than max_frames would be kept they are thinned evenly from the first to the last frame. Off: the first max_frames of every N, which stop before the end of a long clip."),
            ],
            outputs=[
                io.Image.Output(display_name="images"),
                io.String.Output(display_name="frame_indices", tooltip="The kept frames, for example 0, 24, 48. The same text works in the frames of Load Video Advanced."),
            ],
        )

    @classmethod
    def execute(cls, images, every_n, max_frames, spread_to_end) -> io.NodeOutput:
        indices = every_n_frames(images.shape[0], every_n, max_frames, spread_to_end)
        return io.NodeOutput(images[indices], ", ".join(map(str, indices)))


class MajoorRetimeFrames(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorRetimeFrames",
            display_name="Retime Frames",
            category="Majoor/VideoTools",
            description="Play an IMAGE batch taken at one frame rate at another in the same time: frames are dropped or repeated. A control video for a model that generates at 24 fps "
                        "must have its frames at 24 fps, or the take plays the motion slower (or faster) than the source.",
            inputs=[
                io.Image.Input("images"),
                io.Float.Input("fps_in", default=30.0, min=0.01, max=1000.0, step=0.001, tooltip="The frame rate of the images (the fps of Get Video Components)."),
                io.Float.Input("fps_out", default=24.0, min=0.01, max=1000.0, step=0.001, tooltip="The frame rate the next node reads them at."),
                io.Int.Input("min_frames", default=5, min=1, max=1000, optional=True, tooltip="A shorter result is held to this many frames (the last frame repeats). MiniMax H3 refuses a reference video of fewer than 5 frames, which a shot of a fifth of a second or less would give."),
            ],
            outputs=[io.Image.Output(display_name="images"), io.Int.Output(display_name="count")],
        )

    @classmethod
    def execute(cls, images, fps_in, fps_out, min_frames=5) -> io.NodeOutput:
        indices = retime_frames(images.shape[0], fps_in, fps_out, min_frames)
        return io.NodeOutput(images[indices], len(indices))
