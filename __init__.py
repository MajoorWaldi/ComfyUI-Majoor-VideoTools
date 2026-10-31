"""Majoor VideoTools: shot detection, selection, non-destructive replacement and reassembly for ComfyUI."""
# Tests import the package core without ComfyUI installed, so node registration only runs when loaded as a package.
WEB_DIRECTORY = "./web"

if __package__:
    from typing_extensions import override
    from comfy_api.latest import ComfyExtension, io

    from .nodes.apply_shot_metadata import MajoorApplyShotMetadata
    from .nodes.compare_video import MajoorCompareVideo
    from .nodes.deploy_shots import MajoorDeployShots, register_routes
    from .nodes.casting import MajoorApplyCasting
    from .nodes.music_brief import MajoorMusicBrief
    from .nodes.edit_mode import MajoorEditMode, register_routes as register_mode_routes
    from .nodes.audio_rhythm import MajoorAudioRhythm
    from .nodes.get_video_components import MajoorGetVideoComponentsAdvanced
    from .nodes.motion_graphics import MajoorMotionGraphics
    from .nodes.hyperframes_motion import MajoorHyperFrames
    from .nodes.music_fit import MajoorMusicFit
    from .nodes.take_check import MajoorTakeCheck
    from .nodes.check_plate import MajoorCheckPlate
    from .nodes.energy_report import MajoorEnergyReport
    from .nodes.shot_source import MajoorShotSource
    from .nodes.music_direction import MajoorMusicDirection
    from .nodes.yue2_music import MajoorYuE2Style, MajoorYuE2Score
    from .nodes.project_io import MajoorLoadProjectMusic, MajoorLoadShotList, MajoorSaveProjectInfo, MajoorSaveProjectMusic
    from .nodes.load_video_advanced import MajoorLoadVideoAdvanced, register_routes as register_video_routes
    from .nodes.preview_video import MajoorPreviewVideo
    from .nodes.scene_detect_split import MajoorSceneDetectSplit
    from .nodes.select_frames import MajoorSelectEveryNFrames
    from .nodes.select_shot import MajoorSelectShot
    from .nodes.shot_assemble import MajoorShotAssemble
    from .nodes.timeline_edit import MajoorTimelineEdit
    from .nodes.create_timeline import MajoorCreateTimeline, MajoorEnsureBurst
    from .nodes.cut_markers import MajoorCutMarkers
    from .nodes.edit_skills import MajoorEditSkills, register_routes as register_skill_routes

    register_routes()
    register_skill_routes()
    register_video_routes()
    register_mode_routes()

    class MajoorVideoToolsExtension(ComfyExtension):
        @override
        async def get_node_list(self) -> list[type[io.ComfyNode]]:
            return [MajoorSceneDetectSplit, MajoorSelectShot, MajoorApplyShotMetadata, MajoorShotAssemble, MajoorCompareVideo, MajoorPreviewVideo, MajoorLoadVideoAdvanced, MajoorAudioRhythm, MajoorMusicBrief, MajoorEditMode,
                    MajoorCreateTimeline, MajoorEnsureBurst, MajoorCutMarkers, MajoorDeployShots, MajoorEditSkills, MajoorSelectEveryNFrames, MajoorGetVideoComponentsAdvanced, MajoorMotionGraphics, MajoorMusicFit, MajoorTakeCheck, MajoorSaveProjectInfo, MajoorLoadShotList, MajoorSaveProjectMusic, MajoorLoadProjectMusic,MajoorCheckPlate,MajoorEnergyReport,MajoorShotSource,MajoorMusicDirection,MajoorYuE2Style,MajoorYuE2Score,MajoorHyperFrames,MajoorTimelineEdit,MajoorApplyCasting]

    async def comfy_entrypoint() -> MajoorVideoToolsExtension:
        return MajoorVideoToolsExtension()
