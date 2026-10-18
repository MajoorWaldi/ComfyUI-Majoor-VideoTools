from comfy_api.latest import io

from ..adapters.comfy_video import MajoorShotList, projects_root, video_file
from ..core.scene_detection import MODES, detect_scenes
from ..core.timeline import format_timecode
from .preview import shots_payload


class MajoorSceneDetectSplit(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MajoorSceneDetectSplit",
            display_name="Scene Detect & Split",
            category="Majoor/VideoTools",
            description="Detect shot boundaries and index the video as a persistent shot collection. No clip is encoded.",
            is_output_node=True,
            inputs=[
                io.Video.Input("video"),
                io.Combo.Input("detection_mode", options=list(MODES), default="adaptive", tooltip="threshold_fade proposes cuts around fades to black; manual uses cut_points only."),
                io.Float.Input("sensitivity", default=0.5, min=0.0, max=1.0, step=0.01, tooltip="Higher detects more cuts."),
                io.Int.Input("min_shot_frames", default=6, min=1, max=100000, tooltip="Cuts creating shorter shots are merged and reported as warnings."),
                io.String.Input("cut_points", default="", multiline=True, optional=True, tooltip="manual mode: frame numbers, or timecodes (hh:mm:ss.ff, 12.5s), separated by commas or spaces."),
                io.Boolean.Input("preview_thumbnails", default=True),
                io.Boolean.Input("force_refresh", default=False, tooltip="Ignore the detection cache. Shot ids stay the same when the cuts are unchanged."),
            ],
            outputs=[MajoorShotList.Output(display_name="shot_list")],
        )

    @classmethod
    def execute(cls, video, detection_mode, sensitivity, min_shot_frames, cut_points="", preview_thumbnails=True, force_refresh=False) -> io.NodeOutput:
        with video_file(video) as path:
            shot_list = detect_scenes(path, projects_root(), detection_mode, sensitivity, min_shot_frames, cut_points, preview_thumbnails, force_refresh)
        src = shot_list.source
        summary = f"Detected {len(shot_list.shots)} shots · {format_timecode(src.duration_seconds)} · {src.fps_num / src.fps_den:.3f} fps · {src.width}x{src.height}"
        warnings = "".join(f"\n⚠ {w}" for w in shot_list.detection.warnings)
        return io.NodeOutput(shot_list, ui={"text": (summary + warnings,), "majoor_shots": [shots_payload(shot_list)]})
