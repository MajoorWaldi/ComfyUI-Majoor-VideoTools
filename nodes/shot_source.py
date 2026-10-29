import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from comfy_api.latest import io,VideoFromFile

from ..adapters.comfy_video import MajoorShotList,MajoorShotMetadata,projects_root,video_file
from ..core.paths import ProjectStore
from ..core.render_source import parse_render_source,render_planned_source


class MajoorShotSource(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='MajoorShotSource',display_name='Planned Shot Source',category='Majoor/VideoTools',
            inputs=[MajoorShotList.Input('shot_list'),MajoorShotMetadata.Input('metadata'),
                    *[io.Image.Input(f'image{i}',optional=True,lazy=True) for i in range(1,6)],io.Video.Input('provided_video',optional=True,lazy=True)],
            outputs=[io.Boolean.Output(display_name='requires_generation'),io.Video.Output(display_name='local_video')])

    @classmethod
    def check_lazy_status(cls,shot_list,metadata,**kwargs):
        spec=parse_render_source((shot_list.get_shot(metadata.shot_id).plan or {}).get('render_source'))
        field='image'+spec.get('asset','ref1')[3:] if spec['kind']=='still' else 'provided_video' if spec['kind']=='provided' else None
        return [field] if field and kwargs.get(field) is None else []

    @classmethod
    def execute(cls,shot_list,metadata,provided_video=None,**images):
        shot=shot_list.get_shot(metadata.shot_id)
        spec=parse_render_source((shot.plan or {}).get('render_source'))
        if spec['kind']=='generated':return io.NodeOutput(True,None)
        store=ProjectStore(projects_root(),shot_list.project_id)
        with tempfile.TemporaryDirectory(dir=store.dir/'cache') as temp:
            image_path=None
            if spec['kind']=='still':
                image=images.get('image'+spec.get('asset','ref1')[3:])
                if image is not None:
                    image_path=Path(temp)/'image.png'
                    Image.fromarray(np.clip(image[0].cpu().numpy()*255,0,255).astype(np.uint8)).save(image_path)
            if spec['kind']=='provided' and provided_video is not None:
                with video_file(provided_video) as video_path:
                    path=render_planned_source(store,shot,shot_list.source.fps,shot_list.source.width,shot_list.source.height,video=video_path)
            else:path=render_planned_source(store,shot,shot_list.source.fps,shot_list.source.width,shot_list.source.height,image=image_path)
        return io.NodeOutput(False,VideoFromFile(str(path)))
