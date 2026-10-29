"""Advisory text overlap using existing subject masks; never infer a face."""
import math

import numpy as np
from PIL import Image


def subject_overlap(samples, masks, size, duration):
    if masks is None:
        return {'status': 'not_evaluated', 'reason': 'No existing subject masks'}
    data = np.asarray(masks)
    if data.ndim != 3 or not len(data) or not np.isfinite(data).all():
        raise ValueError('Subject masks must be finite non-empty [N,H,W]')
    width, height = size
    observations = []
    for sample in samples:
        index = min(len(data)-1, max(0, int(sample['time'] / duration * len(data))))
        mask = np.asarray(Image.fromarray(data[index].astype(np.float32)).resize((width,height))) > .5
        for kind in ('canvas', 'html'):
            for layer, row in enumerate(sample.get(kind, [])):
                if kind == 'canvas' and row.get('alpha', 0) <= .1:
                    continue
                a,b,c,d = row['rect']
                left,top = max(0,math.floor(a)),max(0,math.floor(b))
                right,bottom = min(width,math.ceil(c)),min(height,math.ceil(d))
                if right <= left or bottom <= top:
                    continue
                area = mask[top:bottom,left:right]
                if not area.size:
                    continue
                fraction = float(area.mean())
                if fraction > .05:
                    observations.append({'time':sample['time'],'kind':kind,'layer':layer,'fraction':round(fraction,4)})
    return {'status':'measured','scope':'Text bounds overlapping existing subject segmentation; no face or legibility guarantee',
            'overlaps':observations}
