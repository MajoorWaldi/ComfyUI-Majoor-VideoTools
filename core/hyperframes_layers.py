"""Prepare masks/geometry/tracking, not rendered graphics. HyperFrames composites."""
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ..adapters.ffmpeg import run_ffmpeg
from .motion import Masks, _Tracker, needs_mask


def prepare_layers(project, source, info, layers, masks=None, cancelled=None):
    if not layers:
        return {}
    required = needs_mask(layers)
    if required and masks is None:
        raise ValueError('These layers need a subject mask: connect BiRefNet or another segmentation node')
    if masks is not None and (masks.ndim != 3 or not len(masks) or not np.isfinite(masks).all()):
        raise ValueError('Subject masks must be a finite non-empty [N,H,W] array')
    width, height = info.display_size
    fps, duration = float(info.fps), float(info.duration)
    count = max(round(duration * fps), 1)
    # Source pixels are needed only for footage effects or optical-flow tracking.
    footage = any(x['type'] == 'effect' for x in layers)
    tracking = any(x['type'] == 'track' for x in layers)
    optical = any(x['type'] == 'track' and not x['anchor'] for x in layers)
    frames = project / 'assets/frames'
    frame_paths = None
    if footage or optical:
        frames.mkdir(parents=True, exist_ok=True)
        effects = [x for x in layers if x['type']=='effect']
        selected = list(range(count)) if optical else [i for i in range(count) if any(x['start'] <= i/fps < (x['end'] if x['end'] is not None else duration) for x in effects)]
        filters = f'fps={info.fps},scale={width}:{height}'
        if not optical and len(selected) < count:
            ranges=[]
            for i in selected:
                if ranges and ranges[-1][1]+1==i: ranges[-1][1]=i
                else: ranges.append([i,i])
            expression='+'.join(f'between(n,{a},{b})' for a,b in ranges) or '0'
            filters += f",select='{expression}'"
            frame_paths=[None]*count
            for sequence,i in enumerate(selected): frame_paths[i]=f'assets/frames/{sequence:06d}.png'
        if selected:
            run_ffmpeg(['-y','-i',str(source),'-vf',filters,'-fps_mode','vfr',
                        '-frames:v',str(len(selected)),'-start_number','0',str(frames/'%06d.png')],duration,None,cancelled)
    mask_dir=project/'assets/masks'
    if required:
        mask_dir.mkdir(parents=True,exist_ok=True)
    subjects=Masks(masks if required else None)
    tracker=_Tracker()
    tracks={str(i):[] for i,x in enumerate(layers) if x['type']=='track'}
    outlines={str(i):{'ring':[],'halo':[]} for i,x in enumerate(layers) if x['type']=='outline'}
    mask_paths=[]
    targeted=any(x['type']=='effect' and x['target']!='frame' for x in layers)
    for index in range(count):
        if cancelled and cancelled():
            raise InterruptedError('HyperFrames layer preparation cancelled')
        t=index/fps
        subject=subjects.at(index,count,width,height) if required else None
        if targeted:
            name=f'assets/masks/subject-{index:06d}.png'
            Image.fromarray((np.clip(subject,0,1)*255).astype(np.uint8)).save(project/name)
            mask_paths.append(name)
        if tracking:
            filename=(project/frame_paths[index]) if frame_paths and frame_paths[index] else frames/f'{index:06d}.png'
            gray=cv2.imread(str(filename),cv2.IMREAD_GRAYSCALE) if optical or (footage and (frame_paths is None or frame_paths[index])) else np.zeros((height,width),np.uint8)
            if gray is None:
                raise ValueError('Cannot read a tracking frame')
            tracker.update(layers,gray,t,subject)
            for key in tracks:
                point=tracker.points.get(id(layers[int(key)]))
                tracks[key].append(None if point is None else [round(float(v),3) for v in point])
        for key,paths in outlines.items():
            layer=layers[int(key)]
            active=layer['start']<=t<(layer['end'] if layer['end'] is not None else duration)
            if not active:
                paths['ring'].append(None);paths['halo'].append(None);continue
            side=min(width,height);thick=max(int(side*layer['width']),1)
            solid=(subject>.5).astype(np.uint8)
            ring=cv2.dilate(solid,np.ones((2*thick+1,2*thick+1),np.uint8))-solid
            if layer['style']=='double':
                ring|=cv2.dilate(solid,np.ones((6*thick+1,6*thick+1),np.uint8))-cv2.dilate(solid,np.ones((4*thick+1,4*thick+1),np.uint8))
            elif layer['style']=='dashed':
                yy,xx=np.mgrid[:height,:width]
                ring*=(((xx+yy+int(t*side*.4))//max(thick*4,4))%2==0)
            name=f'assets/masks/ring-{key}-{index:06d}.png'
            Image.fromarray(ring*255).save(project/name);paths['ring'].append(name)
            glow=max(layer['glow'],.7) if layer['style']=='neon' else layer['glow']
            if glow:
                name=f'assets/masks/halo-{key}-{index:06d}.png'
                halo=cv2.GaussianBlur(ring.astype(np.float32),(0,0),max(thick*3,2))*2.5*glow
                Image.fromarray((np.clip(halo,0,1)*255).astype(np.uint8)).save(project/name)
                paths['halo'].append(name)
            else:paths['halo'].append(None)
    return {'footage':footage,'frame_pattern':'assets/frames/','count':count,'width':width,'height':height,
            'fps':fps,'masks':mask_paths,'outlines':outlines,'tracks':tracks, **({'frame_paths':frame_paths} if frame_paths is not None else {})}
