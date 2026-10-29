"""Small declarative scene vocabulary; no generated executable code."""
import math
from .text_timing import animated_reading_budget

STYLES = {
    'tech': {'font':'clean','color':'#f4f6ff','thickness':.002,'in_time':.20,'ease':'out'},
    'editorial': {'font':'serif','color':'#ece3d2','thickness':.0015,'in_time':.42,'ease':'smooth'},
    'pop': {'font':'impact','color':'#ffe342','thickness':.006,'in_time':.12,'ease':'back'},
}


def graphic_handoff(cut, before=.35, after=.35, *, velocity=(.2,0), at=(.5,.7), color='#e4c081'):
    """Two explicit vector layers that carry position and relative speed across a cut."""
    values=(cut,before,after,*velocity,*at)
    if not all(math.isfinite(v) for v in values) or not .05<=before<=3 or not .05<=after<=3 or cut<before:
        raise ValueError('Graphic handoff needs finite timing and .05–3 second wings inside the video')
    if len(velocity)!=2 or len(at)!=2 or any(abs(v)>1 for v in velocity) or any(not 0<=v<=1 for v in at):
        raise ValueError('Graphic handoff needs normalized point and bounded velocity')
    base={'type':'vector','shape':'dot','at':list(at),'radius':.012,'color':color,
          'animation':'none','out':'none','ease':'linear','sync':'none'}
    return [{**base,'start':cut-before,'end':cut,'in_time':before,
             'motion_from':{'x':-velocity[0]*before,'y':-velocity[1]*before},'motion_to':{'x':0,'y':0}},
            {**base,'start':cut,'end':cut+after,'in_time':after,
             'motion_from':{'x':0,'y':0},'motion_to':{'x':velocity[0]*after,'y':velocity[1]*after}}]


def style_layer(row):
    from .motion_contract import validate_motion_rows
    validate_motion_rows([row])
    design = row.get('design')
    if design is not None and (not isinstance(design,str) or design not in STYLES):
        raise ValueError('Motion design must be tech, editorial or pop')
    for key in ('scene','id','after'):
        if key in row and row[key] is not None and (not isinstance(row[key],str) or len(row[key])>80):
            raise ValueError('Motion scene and dependency names must be short text')
    return {**STYLES.get(design, {}), **row}


def transform(value):
    if not isinstance(value, dict) or set(value)-{'x','y','scale','rotate'}:
        raise ValueError('Motion transform keys: x, y, scale, rotate')
    out={'x':0.,'y':0.,'scale':1.,'rotate':0.}
    for key, raw in value.items():
        number=float(raw)
        if not math.isfinite(number):
            raise ValueError('Motion transform must be finite')
        low,high={'x':(-2,2),'y':(-2,2),'scale':(.05,4),'rotate':(-180,180)}[key]
        out[key]=min(high,max(low,number))
    return out


def readability(layers, width, height, duration):
    """Conservative layout advisories, not semantic approval or face detection."""
    warnings=[]
    for index,row in enumerate(layers):
        if row['type'] not in ('text','emoji'):continue
        length=float(row.get('end') or duration)-float(row.get('start',0))
        required = animated_reading_budget(str(row.get('content', '')), row.get('animation','none'),
                                           float(row.get('in_time',.25)),row.get('out','none'),row.get('repeat',1))
        if length + 1e-6 < required:
            warnings.append({'layer':index,'kind':'short_reading_window'})
        if height*row.get('size',.08)<18:
            warnings.append({'layer':index,'kind':'small_text'})
        # Explicit placement and final motion can defeat the renderer's safe wrapping.
        motion=row.get('motion_to',{})
        if 'x' in row:
            x,y=row['x']+motion.get('x',0),row.get('y',0)+motion.get('y',0)
            if x<0 or x>.92 or y<0 or y+row.get('size',.08)>.95:
                warnings.append({'layer':index,'kind':'possible_clipping'})
    return {'warnings':warnings,'method':'timing, nominal text size and explicit final placement; no semantic or face analysis'}


def sound_events(rows, timeline, duration, fps, hits=()):
    from .motion_timing import shot_layers
    from .sfx import GAINS
    import json
    layers,_=shot_layers(json.dumps(rows),json.dumps(timeline),duration,fps,hits)
    events=[]
    for row in layers:
        if row.get('sfx'):
            if row['sfx'] not in GAINS:raise ValueError('Unknown scene sound effect')
            events.append((row['start'],row['sfx']))
    return events
