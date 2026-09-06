"""Display regions derived from unchanged segmentation probabilities.

All output coordinates/areas are original pixels. Configuration geometry uses
768x768-equivalent pixels so an image's display/export resolution is irrelevant.
"""
from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
import math
import os
import time
import numpy as np
from scipy import ndimage

CLASSES = ('MA', 'HE', 'EX', 'SE')

@dataclass(frozen=True)
class LesionPostprocessConfig:
    pixel_threshold: float = 0.5
    region_threshold: float = 0.5
    minimum_area: dict = field(default_factory=lambda: {'MA': 0.4, 'HE': 2.0, 'EX': 0.4, 'SE': 4.0})
    merge_distance: dict = field(default_factory=lambda: {'MA': 0.0, 'HE': 1.0, 'EX': 0.0, 'SE': 1.0})
    model_size: int = 768

    def __post_init__(self):
        for value in (self.pixel_threshold, self.region_threshold):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Thresholds must be finite and between 0 and 1')
        if self.model_size != 768:
            raise ValueError('Geometry reference must match the deployed 768px model')
        for name in ('minimum_area', 'merge_distance'):
            values = getattr(self, name)
            if set(values) != set(CLASSES) or any(not math.isfinite(v) or v < 0 for v in values.values()):
                raise ValueError(f'{name} must contain nonnegative finite values for MA, HE, EX, SE')

    def metadata(self):
        return {**asdict(self), 'geometry_units': '768x768-equivalent pixels; area in squared pixels',
                'order': '8-connected components -> minimum area -> same-class proximity union -> area-weighted mean score threshold',
                'merge_rule': 'minimum member-pixel center distance; connected groups; no cross-class merging',
                'status': 'Conservative exploratory display settings; not a clinically validated operating point'}


def load_config():
    path = Path(os.environ.get('RETINA_LESION_POSTPROCESS_CONFIG',
                            Path(__file__).resolve().parents[1] / 'config/lesion_postprocessing.json'))
    return LesionPostprocessConfig(**json.loads(path.read_text(encoding='utf-8')))


def _elapsed_ms(started):
    return (time.perf_counter_ns() - started) / 1_000_000


def process_channel(probabilities, code, config, timing=None):
    """Never mutate probabilities or reconstruct/replace its threshold mask."""
    if code not in CLASSES:
        raise ValueError('Unsupported lesion class')
    p = np.asarray(probabilities)
    if p.ndim != 2 or not p.size or not np.isfinite(p).all() or p.min() < 0 or p.max() > 1:
        raise ValueError('Expected finite 2D probabilities in [0,1]')
    timing = timing if timing is not None else {}
    h, w = p.shape
    started = time.perf_counter_ns()
    binary = p >= config.pixel_threshold
    timing['mask_thresholding_ms'] = timing.get('mask_thresholding_ms', 0.0) + _elapsed_ms(started)
    started = time.perf_counter_ns()
    labels, count = ndimage.label(binary, structure=np.ones((3, 3)))
    slices = ndimage.find_objects(labels)
    timing['connected_components_ms'] = timing.get('connected_components_ms', 0.0) + _elapsed_ms(started)
    raw = []
    started = time.perf_counter_ns()
    for label_id, box in enumerate(slices, 1):
        local = labels[box] == label_id
        ys, xs = np.nonzero(local)
        ys, xs = ys + box[0].start, xs + box[1].start
        values = p[box][local]
        area = len(xs)
        raw.append({'region_id': label_id, 'class': code, 'source_component_ids': [label_id],
                    'x_min': int(xs.min()), 'y_min': int(ys.min()), 'x_max': int(xs.max()), 'y_max': int(ys.max()),
                    'width': int(xs.max()-xs.min()+1), 'height': int(ys.max()-ys.min()+1),
                    'center_x': int(np.rint(xs.mean())), 'center_y': int(np.rint(ys.mean())),
                    'centroid_x': float(xs.mean()), 'centroid_y': float(ys.mean()),
                    'area_pixels': area, 'area_model_pixels': area*config.model_size**2/(h*w),
                    'mean_probability': float(values.mean(dtype=np.float64)), 'max_probability': float(values.max())})
    timing['bounding_box_extraction_ms'] = timing.get('bounding_box_extraction_ms', 0.0) + _elapsed_ms(started)
    started = time.perf_counter_ns()
    minimum = max(1, math.ceil(config.minimum_area[code]*h*w/config.model_size**2))
    retained = [r for r in raw if r['area_pixels'] >= minimum]
    parents = {r['region_id']: r['region_id'] for r in retained}
    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    distance = config.merge_distance[code]
    if distance > 0:
        # Local distance transforms examine actual component pixels, not empty
        # overlapping bounding boxes. Sampling compensates for anisotropic resize.
        ry, rx = math.ceil(distance*h/config.model_size), math.ceil(distance*w/config.model_size)
        for r in retained:
            i = r['region_id']
            y0,y1=max(0,r['y_min']-ry),min(h,r['y_max']+ry+1)
            x0,x1=max(0,r['x_min']-rx),min(w,r['x_max']+rx+1)
            local=labels[y0:y1,x0:x1]
            distances=ndimage.distance_transform_edt(local != i, sampling=(config.model_size/h,config.model_size/w))
            neighbors=np.unique(local[distances <= distance])
            for j in neighbors:
                j=int(j)
                if j > i and j in parents:
                    a,b=find(i),find(j)
                    if a != b: parents[max(a,b)] = min(a,b)
    groups = {}
    for r in retained: groups.setdefault(find(r['region_id']), []).append(r)
    merged=[]
    for members in groups.values():
        area=sum(r['area_pixels'] for r in members)
        x1=min(r['x_min'] for r in members); y1=min(r['y_min'] for r in members)
        x2=max(r['x_max'] for r in members); y2=max(r['y_max'] for r in members)
        cx=sum(r['centroid_x']*r['area_pixels'] for r in members)/area
        cy=sum(r['centroid_y']*r['area_pixels'] for r in members)/area
        merged.append({**members[0], 'source_component_ids':[r['region_id'] for r in members],
                       'x_min':x1,'y_min':y1,'x_max':x2,'y_max':y2,'width':x2-x1+1,'height':y2-y1+1,
                       'center_x':int(np.rint(cx)), 'center_y':int(np.rint(cy)), 'centroid_x':cx,'centroid_y':cy,
                       'area_pixels':area, 'area_model_pixels':area*config.model_size**2/(h*w),
                       'mean_probability':sum(r['mean_probability']*r['area_pixels'] for r in members)/area,
                       'max_probability':max(r['max_probability'] for r in members)})
    displayed=sorted((r for r in merged if r['mean_probability'] >= config.region_threshold),
                     key=lambda r:(-r['area_pixels'],-r['mean_probability'],r['region_id']))
    for r in raw + displayed:
        r['bbox_pixels']=[r['x_min'],r['y_min'],r['x_max'],r['y_max']]
        r['center_pixels']=[r['center_x'],r['center_y']]
    timing['region_filtering_ms'] = timing.get('region_filtering_ms', 0.0) + _elapsed_ms(started)
    started = time.perf_counter_ns()
    stats={'raw_region_count':int(count),'removed_by_area':len(raw)-len(retained),
           'merged_components':len(retained)-len(merged), 'removed_by_region_threshold':len(merged)-len(displayed),
           'displayed_region_count':len(displayed), 'minimum_area_original_pixels':minimum}
    timing['lesion_counting_ms'] = timing.get('lesion_counting_ms', 0.0) + _elapsed_ms(started)
    return {'regions':displayed, 'raw_regions':raw, 'num_regions':len(displayed), 'detected':bool(displayed), **stats}


def process_maps(maps, config, timing=None):
    classes={code:process_channel(p,code,config,timing) for code,p in maps.items()}
    keys=('raw_region_count','removed_by_area','merged_components','removed_by_region_threshold','displayed_region_count')
    stats={key:sum(c[key] for c in classes.values()) for key in keys}
    return {'lesions':classes, **stats, 'postprocessing':{**config.metadata(),'statistics':stats}}
