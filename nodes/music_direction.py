import json

from comfy_api.latest import io

from ..core.music_direction import parse_direction


class MajoorMusicDirection(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='MajoorMusicDirection',display_name='Audiovisual Music Direction',category='Majoor/VideoTools',
            inputs=[io.String.Input('assessment',multiline=True),io.String.Input('user_mood',default='',optional=True),io.Int.Input('bpm',default=0,min=0,max=200,optional=True)],
            outputs=[io.String.Output(display_name='prompt'),io.Int.Output(display_name='bpm'),io.Combo.Output(display_name='energy',options=['calm','balanced','intense']),io.Combo.Output(display_name='key',options=[f'{root} {scale}' for root in ('C','C#','Db','D','D#','Eb','E','F','F#','Gb','G','G#','Ab','A','A#','Bb','B') for scale in ('major','minor')]),io.String.Output(display_name='direction_json'),io.String.Output(display_name='moments_json')])

    @classmethod
    def execute(cls,assessment,user_mood='',bpm=0):
        direction=parse_direction(assessment,user_mood,bpm)
        return io.NodeOutput(direction['prompt'],direction['bpm'],direction['energy'],direction['key'],json.dumps(direction),json.dumps(direction['moments']))
