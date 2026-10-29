"""Execute the new nodes on a fresh project, with no generation model."""
import json
import tempfile
from pathlib import Path

import folder_paths
import torch

from MVT.adapters.comfy_video import projects_root
from MVT.core.template import create_template
from MVT.core.paths import ProjectStore
from MVT.core.revisions import make_metadata
from MVT.nodes.check_plate import MajoorCheckPlate
from MVT.nodes.energy_report import MajoorEnergyReport
from MVT.nodes.shot_source import MajoorShotSource

with tempfile.TemporaryDirectory(prefix='secator_katana_nodes_') as directory:
    folder_paths.get_output_directory=lambda:directory
    shots=create_template(json.dumps({'shots':[{'id':'TITLE','duration':1,'render_source':{'kind':'graphic','text':'HELLO'}}]}),projects_root(),fps=24,aspect_ratio='1:1',resolution=128,profile='minimax_h3',thumbnails=False)
    shot=shots.shots[0]
    metadata=make_metadata(shots,shot,shot.revision(shot.active_revision_id))
    plate=MajoorCheckPlate.execute('{"status":"person","reason":"a reflection"}',image=torch.ones(1,64,64,3),metadata=metadata)
    assert plate.args[0] is None and plate.args[1]=='person'
    source=MajoorShotSource.execute(shots,metadata)
    assert source.args[0] is False
    MajoorEnergyReport.execute(source.args[1],shots)
    store=ProjectStore(projects_root(),shots.project_id)
    measured=store.read_json('exports/energy.json')['result']['duration_seconds']
    assert abs(measured-shot.target_duration_seconds)<1/24,(measured,shot.target_duration_seconds,shots.source.fps,source.args[1].get_stream_source())
    assert store.read_json(f'logs/plate_checks/{shot.shot_id}.json')['status']=='person'
    graphic_video=source.args[1]
    shot.plan['render_source']={'kind':'still','asset':'ref1'}
    still=MajoorShotSource.execute(shots,metadata,image1=torch.ones(1,64,64,3))
    assert still.args[0] is False
    shot.plan['render_source']={'kind':'provided','asset':'ref_video'}
    provided=MajoorShotSource.execute(shots,metadata,provided_video=graphic_video)
    assert provided.args[0] is False
    print('katana nodes: fresh project plate/source/energy OK')
