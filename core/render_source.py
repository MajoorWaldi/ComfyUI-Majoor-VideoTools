"""Render explicitly planned graphics/stills/clips without a video generation model."""
from pathlib import Path

from PIL import Image,ImageColor,ImageDraw

from ..adapters.ffmpeg import run_ffmpeg
from .errors import MajoorError
from .fingerprints import file_fingerprint,json_fingerprint
from .fx import _font
from .media_probe import probe

KINDS=('generated','graphic','still','provided')


def parse_render_source(value) -> dict:
    if value is None:return {'kind':'generated'}
    if isinstance(value,str):value={'kind':value}
    if not isinstance(value,dict) or value.get('kind') not in KINDS:
        raise MajoorError('render_source.kind must be generated, graphic, still or provided')
    spec=dict(value)
    if spec['kind']=='still' and spec.get('asset','ref1') not in tuple(f'ref{i}' for i in range(1,6)):
        raise MajoorError('A still source must name ref1 through ref5')
    if spec['kind']=='provided' and spec.get('asset','ref_video')!='ref_video':
        raise MajoorError('A provided source must name ref_video')
    if spec['kind']=='graphic':
        try:ImageColor.getrgb(str(spec.get('color','#101018')))
        except ValueError as error:raise MajoorError('Invalid graphic background color') from error
        if not isinstance(spec.get('text',''),str):raise MajoorError('Graphic text must be a string')
    return spec


def render_planned_source(store,shot,fps,width,height,image:Path|None=None,video:Path|None=None) -> Path:
    spec=parse_render_source((shot.plan or {}).get('render_source'))
    if spec['kind']=='generated':raise MajoorError('This shot requires video generation')
    source=image if spec['kind']=='still' else video if spec['kind']=='provided' else None
    if spec['kind']!='graphic' and (source is None or not source.is_file()):raise MajoorError('The selected source asset was not supplied')
    frames=round(shot.target_duration_seconds*float(fps))
    seconds=frames/float(fps)
    key=json_fingerprint([spec,frames,str(fps),width,height,file_fingerprint(source) if source else None])[:24]
    out=store.resolve(f'cache/render_sources/{key}.mp4')
    with store.lock():
        if out.is_file():return out
        out.parent.mkdir(parents=True,exist_ok=True)
        if spec['kind']=='graphic':
            canvas=Image.new('RGB',(width,height),spec.get('color','#101018'))
            text=spec.get('text','')
            if text:
                draw=ImageDraw.Draw(canvas);font=_font(max(12,round(min(width,height)*.09)))
                draw.multiline_text((width/2,height/2),text,fill='white',font=font,anchor='mm',align='center',spacing=8)
            source=out.with_suffix('.png');canvas.save(source)
        still=spec['kind'] in ('graphic','still')
        inputs=['-loop','1','-framerate',str(float(fps))] if still else []
        filters=f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={fps},tpad=stop_mode=clone:stop_duration={seconds},trim=end_frame={frames},setpts=PTS-STARTPTS'
        tmp=out.with_suffix('.partial.mp4')
        audio=not still and probe(source,with_packets=False).has_audio
        args=['-y',*inputs,'-i',str(source),'-vf',filters,'-map','0:v:0','-c:v','libx264','-pix_fmt','yuv420p']
        args+=['-map','0:a:0','-af','apad','-c:a','aac'] if audio else ['-an']
        try:
            run_ffmpeg([*args,'-t',str(seconds),str(tmp)])
            if probe(tmp,with_packets=False).frame_count!=frames:raise MajoorError('Rendered source has the wrong frame count')
            tmp.replace(out)
        finally:tmp.unlink(missing_ok=True)
    return out
