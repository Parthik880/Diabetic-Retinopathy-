"""Verify the exact former 114-region image against its cached prediction."""
from pathlib import Path
import json
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
before=json.loads((ROOT/'work/runs/f8d8bd0cf8c44399b4ceeee0afabfeab/response.json').read_text())
after=json.loads((ROOT/'work/integration-test.json').read_text())['result']
def local(url): return ROOT/'work/runs'/url.removeprefix('/artifacts/')
assert sum(x['num_regions'] for x in before['lesions']['lesions'].values())==114
for code,item in after['lesions']['lesions'].items():
    p=np.load(local(item['probability_values_path']))
    old=np.load(local(before['lesions']['lesions'][code]['probability_values_path']))
    np.testing.assert_array_equal(p,old)
    assert item['raw_region_count'] == len(item['raw_regions'])
    assert item['displayed_region_count'] == len(item['regions'])
    assert item['raw_region_count']-item['removed_by_area']-item['merged_components']-item['removed_by_region_threshold']==item['displayed_region_count']
assert before['grading']['predicted_grade']==after['grading']['predicted_grade']
stats=after['lesions']['postprocessing']['statistics']
record={'before_run':before['run_id'],'after_run':after['run_id'],'legacy_display_count':114,
        **stats, 'config':after['lesions']['postprocessing'],
        'checks':['bit-identical probabilities to pre-change inference','raw/display count conservation','unchanged predicted grade'],
        'per_class':{code:{key:item[key] for key in [*stats,'minimum_area_original_pixels']} for code,item in after['lesions']['lesions'].items()}}
(ROOT/'work/postprocessing-regression.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record,indent=2))
