from comfy_api.latest import io

from ..adapters.comfy_video import MajoorShotMetadata,projects_root
from ..core.paths import ProjectStore
from ..core.plate_quality import parse_plate_assessment


class MajoorCheckPlate(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='MajoorCheckPlate',display_name='Check Location Plate',category='Majoor/VideoTools',
            inputs=[io.String.Input('assessment',default='',multiline=True),io.Image.Input('image',optional=True),MajoorShotMetadata.Input('metadata',optional=True)],
            outputs=[io.Image.Output(display_name='plate'),io.String.Output(display_name='status'),io.String.Output(display_name='reason')])

    @classmethod
    def execute(cls,assessment,image=None,metadata=None):
        result=parse_plate_assessment(assessment) if image is not None else {'status':'uncertain','reason':'No location image was provided'}
        if metadata is not None:
            store=ProjectStore(projects_root(),metadata.project_id)
            store.write_json(f'logs/plate_checks/{metadata.shot_id}.json',result)
        return io.NodeOutput(image if result['status']=='clear' else None,result['status'],result['reason'],ui={'text':[result['status']+': '+result['reason']]})
