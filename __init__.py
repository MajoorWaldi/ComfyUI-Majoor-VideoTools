"""Majoor VideoTools: shot detection, selection, non-destructive replacement and reassembly for ComfyUI."""
# Tests import the package core without ComfyUI installed, so node registration only runs when loaded as a package.
WEB_DIRECTORY = "./web"

if __package__:
    from typing_extensions import override
    from comfy_api.latest import ComfyExtension, io

    from .nodes.apply_shot_metadata import MajoorApplyShotMetadata
    from .nodes.compare_video import MajoorCompareVideo
    from .nodes.scene_detect_split import MajoorSceneDetectSplit
    from .nodes.select_shot import MajoorSelectShot
    from .nodes.shot_assemble import MajoorShotAssemble

    class MajoorVideoToolsExtension(ComfyExtension):
        @override
        async def get_node_list(self) -> list[type[io.ComfyNode]]:
            return [MajoorSceneDetectSplit, MajoorSelectShot, MajoorApplyShotMetadata, MajoorShotAssemble, MajoorCompareVideo]

    async def comfy_entrypoint() -> MajoorVideoToolsExtension:
        return MajoorVideoToolsExtension()
