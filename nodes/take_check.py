from comfy_api.latest import io

from ..adapters.comfy_video import video_file
from ..core.take_check import check_take


class MajoorTakeCheck(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorTakeCheck",
            display_name="Take Check",
            category="Majoor/VideoTools",
            description="Look at a generated take (eight frames) and say whether it is usable: a take that is black or white from start to end, or only noise, is not. "
                        "Dark, busy and still shots pass; a smeared face does not get caught. Connect ok to a switch that generates the shot again with another seed.",
            inputs=[io.Video.Input("video")],
            outputs=[io.Boolean.Output(display_name="ok"), io.String.Output(display_name="report", tooltip="What is wrong, or the numbers read from a take that is fine.")],
        )

    @classmethod
    def execute(cls, video) -> io.NodeOutput:
        with video_file(video) as path:
            ok, report = check_take(path)
        return io.NodeOutput(ok, report)
