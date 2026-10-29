import json
import re
import os

import comfy.model_management
import comfy.utils
from comfy_api.latest import VideoFromFile, io

from ..adapters.comfy_video import projects_root, video_file
from ..core.hyperframes import render_hyperframes
from ..core.motion import parse_layers, needs_mask


class MajoorHyperFrames(io.ComfyNode):
    @classmethod
    def fingerprint_inputs(cls, enabled=False, layers='[]', source_layers_enabled=False, **kwargs):
        if not enabled and layers.strip() in ('', '[]') and not source_layers_enabled:
            return 'disabled'
        from pathlib import Path
        from ..core.fingerprints import file_fingerprint
        web = Path(__file__).resolve().parents[1] / 'web'
        core = web.parent / 'core'
        return ''.join(file_fingerprint(path) for path in (web / 'hyperframes_scene.html', web / 'hyperframes_layers.js', core / 'hyperframes.py', core / 'motion_timing.py', core / 'motion_scenes.py'))

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id='MajoorHyperFrames', display_name='Motion Design — HyperFrames', category='Majoor/VideoTools',
            description='Optional local finishing pass after assembly. Prepared animations follow measured final audio; no hosted API or generated JavaScript. Original video is retained.',
            inputs=[io.Video.Input('video'), io.Boolean.Input('enabled', default=False),
                    io.String.Input('direction', default='editorial', multiline=True, tooltip='Plain brief selects minimal/editorial/energetic and an optional #RRGGBB accent. JSON: {"preset":"editorial","accent":"#e4c081","reactive":true,"intensity":0.6,"title":"YOUR TEXT"}. No text is invented.'),
                    io.String.Input('shot_cues', default='[]', multiline=True, tooltip='Optional JSON array: [{"shot_id":"SHOT_001","text":"TITLE","position":"top"}]. Or use start/end in final-video seconds. Text only; no HTML/JS.'),
                    io.String.Input('source_layers', default='[]', multiline=True, lazy=True, optional=True),
                    io.Boolean.Input('source_layers_enabled', default=False, optional=True),
                    io.String.Input('project_id', default='', optional=True),
                    io.String.Input('layers', default='[]', multiline=True, optional=True, tooltip='Shared Motion Graphics JSON. Optional shot_id uses local start/end seconds or percentages; sync="onset" aligns the entrance to a measured nearby audio attack.'),
                    io.Mask.Input('mask', optional=True, lazy=True),
                    io.String.Input('timeline', default='[]', multiline=True, tooltip='Actual final timing: [{"id":"SHOT_001","start":0,"duration":3}]. Required for cues addressed by shot_id. start/end always use final-video seconds.')],
            outputs=[io.Video.Output(display_name='video'), io.String.Output(display_name='info')])

    @classmethod
    def check_lazy_status(cls, layers='[]', mask=None, source_layers=None, source_layers_enabled=False, **kwargs):
        if source_layers_enabled and source_layers is None:
            return ['source_layers']
        parsed = parse_layers(layers, 1.0) + (parse_layers(source_layers or '[]', 1.0) if source_layers_enabled else [])
        return ['mask'] if mask is None and needs_mask(parsed) else []

    @classmethod
    def execute(cls, video, enabled=False, direction='editorial', shot_cues='[]', timeline='[]', layers='[]', mask=None, source_layers='[]', source_layers_enabled=False, project_id=''):
        if project_id and not re.fullmatch(r'p_[0-9a-f]{8,32}', project_id):
            raise ValueError('Invalid project id for finishing report')
        if not enabled and not parse_layers(layers, 1.0) and not source_layers_enabled:
            return io.NodeOutput(video, 'HyperFrames disabled: original video unchanged')
        if not enabled:
            direction = '{"preset":"minimal","reactive":false,"intensity":0}'
            shot_cues = '[]'
        bar = comfy.utils.ProgressBar(1000)
        with video_file(video) as source:
            from ..core.media_probe import probe
            duration = float(probe(source, with_packets=False).duration)
            def rows(text):
                data = json.loads(text or '[]')
                return data.get('layers', []) if isinstance(data, dict) else data
            merged = (rows(source_layers) if source_layers_enabled else []) + rows(layers)
            masks = mask.cpu().numpy() if mask is not None and needs_mask(parse_layers(json.dumps(merged), duration)) else None
            output, report = render_hyperframes(source, projects_root(), direction, shot_cues, timeline,
                layers_text=json.dumps(merged), masks=masks, cancelled=comfy.model_management.processing_interrupted,
                progress=lambda value: bar.update_absolute(round(value * 1000), 1000))
        if project_id:
            report_path = projects_root() / project_id / 'exports/hyperframes.json'
            report_path.parent.mkdir(parents=True, exist_ok=True)
            import tempfile
            fd, temporary = tempfile.mkstemp(dir=report_path.parent, suffix='.json')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(report, stream)
                os.replace(temporary, report_path)
            finally:
                from pathlib import Path
                Path(temporary).unlink(missing_ok=True)
        return io.NodeOutput(VideoFromFile(str(output)), json.dumps(report, ensure_ascii=False),
                             ui={'text': (f'HyperFrames: {output}\nOriginal retained. ' + ('Reused existing render.' if report['reused'] else 'Rendered locally.'),)})
