import json

from comfy_api.latest import io

from ..adapters.comfy_video import video_file
from ..core.lipsync import measure_video, needs_retake, next_seed, parse_region


class MajoorLipSyncCheck(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorLipSyncCheck",
            display_name="Lip Sync Check",
            category="Majoor/VideoTools",
            description="Measure whether the mouth of a take moves when the voice sounds: the movement of the mouth region is compared with the loudness of the sound, frame by frame, "
                        "allowing a delay of up to a quarter of a second. It measures movement, not phonemes. Take without a face or without a voice: unmeasured, never a failure. "
                        "Connect retake to a switch that makes the shot again with next_seed.",
            inputs=[
                io.Video.Input("video"),
                io.Int.Input("seed", default=42, min=0, max=0xffffffffffffffff, tooltip="The seed this take was made with."),
                io.Int.Input("attempt", default=1, min=1, max=20, tooltip="Which try this is, from 1."),
                io.Int.Input("max_attempts", default=3, min=1, max=20, tooltip="After this many tries the best take is kept, even when it fails."),
                io.String.Input("mouth_region", default="", optional=True, tooltip='Empty: the face is found on every frame. Or "x,y,w,h" as fractions of the frame (for example 0.35,0.55,0.3,0.2) for a take framed the same way throughout; needed when this OpenCV has no face detector.'),
            ],
            outputs=[
                io.Boolean.Output(display_name="ok", tooltip="False only for a take that was measured and failed."),
                io.Boolean.Output(display_name="retake", tooltip="True when the take failed and tries remain."),
                io.Int.Output(display_name="next_seed", tooltip="The seed for the next try."),
                io.String.Output(display_name="report", tooltip="JSON: status, reason, score, lag_ms, face_ratio, speech_ratio."),
            ],
        )

    @classmethod
    def execute(cls, video, seed=42, attempt=1, max_attempts=3, mouth_region="") -> io.NodeOutput:
        region = parse_region(mouth_region)
        with video_file(video) as path:
            report = measure_video(path, region=region)
        retake = needs_retake(report, attempt, max_attempts)
        return io.NodeOutput(report["status"] != "fail", retake, next_seed(seed, attempt), json.dumps(report),
                             ui={"text": (f"{report['status']}: {report['reason']}" + (f" (score {report['score']}, delay {report['lag_ms']} ms)" if report["score"] is not None else ""),)})
