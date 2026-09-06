import sys
from pathlib import Path
import unittest
from dataclasses import replace
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inference.lesion_postprocessing import LesionPostprocessConfig, process_channel, process_maps

class RegionsTest(unittest.TestCase):
    def config(self, minimum=3, distance=0, score=.6):
        # Native 768px fixture makes geometric configuration exact.
        return LesionPostprocessConfig(region_threshold=score, minimum_area={c:minimum for c in ('MA','HE','EX','SE')},
                                       merge_distance={c:distance for c in ('MA','HE','EX','SE')})
    def test_area_score_and_coordinates(self):
        p=np.zeros((768,768),dtype=np.float32)
        p[10,20]=.99
        p[20:22,30:33]=.8
        p[40:43,50:53]=.55
        original=p.copy(); output=process_channel(p,'HE',self.config())
        self.assertEqual((output['raw_region_count'],output['removed_by_area'],output['removed_by_region_threshold'],output['num_regions']),(3,1,1,1))
        region=output['regions'][0]
        self.assertEqual([region[k] for k in ['x_min','y_min','x_max','y_max','width','height','area_pixels','center_x','center_y']],[30,20,32,21,3,2,6,31,20])
        np.testing.assert_array_equal(p,original)
        self.assertAlmostEqual(region['mean_probability'],.8,places=6)
        self.assertAlmostEqual(region['max_probability'],.8,places=6)
    def test_union_scores_member_pixels_only(self):
        p=np.zeros((768,768),dtype=np.float32)
        p[10:12,10:12]=.8; p[10:12,13:16]=.6
        output=process_channel(p,'HE',self.config(minimum=1,distance=2,score=.65))
        self.assertEqual(output['num_regions'],1)
        r=output['regions'][0]
        self.assertEqual(r['area_pixels'],10) # excludes empty gap and bounding-box background
        self.assertEqual(r['width'],6)
        self.assertAlmostEqual(r['mean_probability'],.68,places=6)
        self.assertEqual(r['source_component_ids'],[1,2])
        self.assertEqual(output['merged_components'],1)
    def test_no_cross_class_or_far_merge(self):
        p=np.zeros((768,768),dtype=np.float32); p[5:7,5:7]=.9; p[100:102,100:102]=.9
        result=process_maps({'HE':p,'MA':p.copy()},self.config(distance=2))
        self.assertEqual(result['displayed_region_count'],4)
        self.assertEqual(result['merged_components'],0)
    def test_geometry_scales_to_original(self):
        p=np.zeros((768,768),dtype=np.float32); p[30:32,40:42]=.8
        a=process_channel(p,'MA',self.config(minimum=4))
        b=process_channel(np.repeat(np.repeat(p,2,axis=0),3,axis=1),'MA',self.config(minimum=4))
        self.assertEqual(a['num_regions'],b['num_regions'])
        r=b['regions'][0]
        self.assertEqual([r['x_min'],r['y_min'],r['width'],r['height'],r['area_pixels']],[120,60,6,4,24])
        self.assertEqual(r['area_model_pixels'],a['regions'][0]['area_model_pixels'])
    def test_ma_merge_disabled_and_small_component_preserved(self):
        p=np.zeros((768,768),dtype=np.float32); p[2,2]=.9;p[2,4]=.9
        output=process_channel(p,'MA',LesionPostprocessConfig())
        self.assertEqual(output['num_regions'],2)
    def test_empty_and_threshold_independence(self):
        p=np.zeros((768,768),dtype=np.float32);p[4:6,4:6]=.7
        a=process_channel(p,'EX',self.config(score=.6))
        b=process_channel(p,'EX',self.config(score=.8))
        self.assertEqual(a['raw_regions'],b['raw_regions'])
        self.assertEqual(b['num_regions'],0)
        self.assertEqual(process_channel(np.zeros_like(p),'EX',self.config())['num_regions'],0)
    def test_invalid_config_and_probabilities(self):
        with self.assertRaises(ValueError): replace(self.config(),region_threshold=float('nan'))
        with self.assertRaises(ValueError): process_channel(np.full((2,2),np.nan),'MA',self.config())

if __name__=='__main__': unittest.main()
