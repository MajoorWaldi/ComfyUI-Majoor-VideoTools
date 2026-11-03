from comfy_api.latest import io

import math
from fractions import Fraction

from ..adapters.comfy_video import video_file
from ..core import energy
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


class MajoorSourceCopy(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorSourceCopy",
            display_name="Source Copy",
            category="Majoor/VideoTools",
            description="Say which of two takes, generated with their source shot as reference video, still repeats that source (the person it was asked to "
                        "replace) over the part the edit keeps. No model: the frames of each take are compared with the frames of the source shot. A take "
                        f"repeats the source when it stays under {energy.COPY_NEAR:g} from it, or {energy.COPY_JUMP:g} closer to it than the other take.",
            inputs=[
                io.Video.Input("take_a"),
                io.Video.Input("take_b", optional=True),
                io.Video.Input("source", tooltip="The source shot the takes were generated from (Select Shot)."),
                io.Float.Input("max_seconds", default=0.0, min=0.0, max=86400.0, step=0.01, optional=True, tooltip="The part of a take the edit keeps: its first max_seconds. 0: the whole take."),
            ],
            outputs=[io.Boolean.Output(display_name="a_copies"), io.Boolean.Output(display_name="b_copies"),
                     io.String.Output(display_name="report", tooltip="The distance of each take to the source: the mean difference (of 255) of each kept frame to the closest source frame.")],
        )

    @classmethod
    def execute(cls, take_a, source, take_b=None, max_seconds=0.0) -> io.NodeOutput:
        with video_file(source) as source_path:
            frames = energy.read_gray(source_path, Fraction(source.get_frame_rate()).limit_denominator(1001))
        distances = []
        for take in (take_a, take_b):
            if take is None:
                continue
            with video_file(take) as take_path:
                rate = Fraction(take.get_frame_rate()).limit_denominator(1001)
                head = math.ceil(max_seconds * float(rate)) if max_seconds > 0 else None
                distances.append(energy.source_likeness(energy.read_gray(take_path, rate, limit=head), frames))
        copies = energy.copying_takes(distances) + [False]
        report = ", ".join(f"take {name} {d:.1f}" + (" (repeats the source)" if c else "") for name, d, c in zip("AB", distances, copies))
        return io.NodeOutput(copies[0], copies[1], report, ui={"text": (report,)})
