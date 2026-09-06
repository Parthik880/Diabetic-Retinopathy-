"""Verify model-derived visualization arrays and image alignment on saved run."""
from pathlib import Path
import json
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
record=json.loads((ROOT/'work/integration-test.json').read_text())
result=record['result']
def local(url): return ROOT/'work/runs'/url.removeprefix('/artifacts/')
shape=(result['image_height'],result['image_width'])
grade=result['grading']['gradcam']
assert grade['target_layer']=='model.features.7.2.block.0'
assert grade['target_class']==result['grading']['predicted_class']
arrays=[]
for code, output in result['lesions']['lesions'].items():
    with Image.open(local(output['mask_path'])) as source, Image.open(local(output['mask_png_path'])) as png, Image.open(local(output['mask_layer_path'])) as rgba:
        binary=np.asarray(source)
        assert np.array_equal(binary,np.asarray(png))
        assert np.array_equal(binary,np.asarray(rgba)[...,3])
        assert np.asarray(png).shape==shape
    probability=np.load(local(output['probability_heatmap']['values_path']),allow_pickle=False)
    original_probability=np.load(local(output['probability_values_path']),allow_pickle=False)
    assert np.array_equal(probability,original_probability)
    if result['lesions'].get('postprocessing'):
        assert np.array_equal(binary > 0, probability >= result['lesions']['threshold']), 'Display filters altered full mask'
    assert probability.shape==shape and np.isfinite(probability).all()
    if output['attention']:
        assert output['attention']['target_layer']=='conv0_3.layers[3]'
        attention=np.load(local(output['attention']['values_path']),allow_pickle=False)
        assert attention.shape==shape and np.isfinite(attention).all()
        assert not np.array_equal(attention,probability), 'Probability mislabeled Grad-CAM'
        arrays.append(attention)
    for region in output['regions']:
        assert region['width']==region['x_max']-region['x_min']+1
        assert region['height']==region['y_max']-region['y_min']+1
grade_array=np.load(local(grade['values_path']),allow_pickle=False)
assert grade_array.shape==shape
assert all(not np.array_equal(grade_array,array) for array in arrays)
with Image.open(ROOT/'resources/test-images/20170629163635747.jpg') as original, Image.open(local(result['image_url'])) as saved:
    assert np.array_equal(np.array(original.convert('RGB')),np.array(saved))
report={'run':result['run_id'],'dimensions':list(shape),'checks':['original RGB pixels preserved','grade final convolution metadata',
    'grade and lesion CAMs distinct','lesion probability arrays unchanged','browser masks pixel-identical to TIFF',
    'RGBA alpha equals original binary mask','all images original resolution','inclusive box dimensions'], 'passed':True}
(ROOT/'work/visual-artifact-test.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
