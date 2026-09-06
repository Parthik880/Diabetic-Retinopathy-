"""Evaluate cached probability maps; no model, weights, or dataset writes.

GT masks are optional and must be explicitly paired, same-resolution binary TIFFs.
Region metrics use 8-connected annotation proxies, not claimed clinical instances.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy import ndimage, sparse
from scipy.sparse.csgraph import maximum_bipartite_matching

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inference.lesion_postprocessing import load_config, process_maps
from models.lesion.dataset import read_annotation

def artifact(value, runs_root):
    return runs_root/value.removeprefix('/artifacts/') if value.startswith('/artifacts/') else Path(value)

def pixel_metrics(pred, truth):
    tp=int(np.count_nonzero(pred & truth)); fp=int(np.count_nonzero(pred & ~truth)); fn=int(np.count_nonzero(~pred & truth))
    ratio=lambda a,b: a/b if b else None
    return {'dice':ratio(2*tp,2*tp+fp+fn),'iou':ratio(tp,tp+fp+fn),
            'recall':ratio(tp,tp+fn),'precision':ratio(tp,tp+fp)}

def evaluate(result, maps, truths, config, match_iou):
    processed=process_maps(maps, config)
    metrics={}
    for code,p in maps.items():
        if code not in truths: continue
        gt=truths[code]
        raw,n=ndimage.label(p >= config.pixel_threshold, np.ones((3,3)))
        lookup=np.zeros(n+1,dtype=np.int32)
        regions=processed['lesions'][code]['regions']
        for i,r in enumerate(regions,1): lookup[r['source_component_ids']]=i
        displayed=lookup[raw]
        gt_labels,gt_n=ndimage.label(gt,np.ones((3,3)))
        # Exact pixel IoU of member masks, not box IoU; maximum one-to-one matching.
        pred_area=np.bincount(displayed.ravel(),minlength=len(regions)+1)[1:]
        gt_area=np.bincount(gt_labels.ravel(),minlength=gt_n+1)[1:]
        overlap=(displayed>0)&(gt_labels>0)
        pairs=displayed[overlap]*(gt_n+1)+gt_labels[overlap]
        joint=np.bincount(pairs,minlength=(len(regions)+1)*(gt_n+1)).reshape(len(regions)+1,gt_n+1)[1:,1:]
        union=pred_area[:,None]+gt_area[None,:]-joint
        ious=np.divide(joint,union,out=np.zeros_like(joint,dtype=float),where=union>0)
        matches=int(np.count_nonzero(maximum_bipartite_matching(sparse.csr_matrix(ious>=match_iou),perm_type='column')>=0)) if len(regions) and gt_n else 0
        metrics[code]={'raw_pixel':pixel_metrics(p>=config.pixel_threshold,gt),
                       'retained_member_pixels':pixel_metrics(displayed>0,gt),
                       'annotation_components':gt_n,'matched_components':matches,
                       'component_proxy_precision':matches/len(regions) if regions else None,
                       'component_proxy_recall':matches/gt_n if gt_n else None,
                       'unmatched_predicted_regions_per_image':len(regions)-matches}
    return {**processed,'metrics':metrics}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result',type=Path,required=True,help='response.json or integration-test.json')
    parser.add_argument('--runs-root',type=Path,default=ROOT.parent/'work/runs')
    parser.add_argument('--ground-truth',action='append',default=[],metavar='MA=path.tif')
    parser.add_argument('--thresholds',type=float,nargs='+',default=[.4,.5,.6,.7,.8,.9],help='Region display thresholds; pixel threshold unchanged')
    parser.add_argument('--match-iou',type=float,default=.1)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 0 < args.match_iou <= 1: parser.error('--match-iou must be in (0,1]')
    result=json.loads(args.result.read_text()); result=result.get('result',result)
    maps={c:np.load(artifact(v['probability_values_path'],args.runs_root),allow_pickle=False) for c,v in result['lesions']['lesions'].items()}
    truths={}
    for pair in args.ground_truth:
        code,path=pair.split('=',1)
        if code not in maps: parser.error('Ground-truth class must match an available model channel')
        array,_=read_annotation(path,expected_size=(maps[code].shape[1],maps[code].shape[0]))
        truths[code]=array>0
    started=time.perf_counter(); candidates=[]; config=load_config()
    for threshold in args.thresholds:
        assessed=evaluate(result,maps,truths,replace(config,region_threshold=threshold),args.match_iou)
        candidates.append({'region_threshold':threshold,'statistics':assessed['postprocessing']['statistics'],
                           'per_class':{c:{k:v for k,v in item.items() if k not in ('regions','raw_regions')} for c,item in assessed['lesions'].items()},
                           'metrics':assessed['metrics']})
    selected=evaluate(result,maps,truths,config,args.match_iou)
    record={'input_run':result['run_id'],'legacy_count':sum(v['num_regions'] for v in result['lesions']['lesions'].values()),
            'config':config.metadata(),'ground_truth':args.ground_truth,'component_matching_iou':args.match_iou,
            'metric_scope':'Per-class pixel metrics; region metrics are one-to-one 8-connected annotation-component proxies. Missing masks are unmeasured, never negatives. Same-image exploratory evaluation, not independent validation.',
            'candidates':candidates,'selected':selected,'seconds':time.perf_counter()-started}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(record,indent=2))
    print(json.dumps({'selected':selected['postprocessing']['statistics'],'seconds':record['seconds'],
                      'candidates':[{'threshold':r['region_threshold'],**r['statistics'],'metrics':r['metrics']} for r in candidates]},indent=2))

if __name__=='__main__': main()
