from comfy_api.latest import io

from ..adapters.comfy_video import preview_ref

MODES = ["wipe", "side_by_side"]


class MajoorCompareVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorCompareVideo",
            display_name="Majoor Compare Video",
            category="Majoor/VideoTools",
            description="Play two videos in sync inside the node, with a wipe slider or side by side.",
            is_output_node=True,
            inputs=[
                io.Video.Input("video_a"),
                io.Video.Input("video_b"),
                io.Combo.Input("mode", options=MODES, default="wipe"),
                io.String.Input("label_a", default="A"),
                io.String.Input("label_b", default="B"),
            ],
            outputs=[],
        )

    @classmethod
    def execute(cls, video_a, video_b, mode, label_a, label_b) -> io.NodeOutput:
        return io.NodeOutput(ui={"majoor_compare": [{"a": preview_ref(video_a), "b": preview_ref(video_b)}]})
