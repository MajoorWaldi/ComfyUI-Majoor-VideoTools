import json
from comfy_api.latest import io
from ..core.yue2_music import music_style, music_score


class MajoorYuE2Style(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='MajoorYuE2Style',display_name='YuE2 Music Direction',category='Majoor/VideoTools',
            inputs=[io.String.Input('prompt',multiline=True),io.Int.Input('bpm',default=120,min=0,max=300),io.Combo.Input('key',options=[f'{root} {scale}' for root in ('C','C#','Db','D','D#','Eb','E','F','F#','Gb','G','G#','Ab','A','A#','Bb','B') for scale in ('major','minor')],default='C major'),io.String.Input('lyrics',default='',multiline=True,optional=True)],
            outputs=[io.String.Output(display_name='style'),io.String.Output(display_name='lyrics'),io.Boolean.Output(display_name='instrumental')])

    @classmethod
    def execute(cls,prompt,bpm=120,key='C major',lyrics=''):
        return io.NodeOutput(*music_style(prompt,bpm,key,lyrics))


class MajoorYuE2Score(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='MajoorYuE2Score',display_name='YuE2 Prepare Score',category='Majoor/VideoTools',
            inputs=[io.String.Input('abc',multiline=True),io.Boolean.Input('instrumental',default=True)],
            outputs=[io.String.Output(display_name='abc'),io.String.Output(display_name='info')])

    @classmethod
    def execute(cls,abc,instrumental=True):
        score,report=music_score(abc,instrumental)
        return io.NodeOutput(score,json.dumps(report))
