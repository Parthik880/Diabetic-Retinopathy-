from pathlib import Path
import json
from PIL import Image,ImageChops
folder=Path('build/validation/model-modularity')
ignore={'model_initialization_ms','analysis_ms','timing_ms'}
def normalized(value):
    if isinstance(value,dict):return {k:normalized(v) for k,v in value.items() if k not in ignore}
    if isinstance(value,list):return [normalized(v) for v in value]
    if isinstance(value,str) and '/runs/' in value.replace('\\','/'):
        return value.replace('\\','/').split('/runs/',1)[1].split('/',1)[-1]
    return value

def differences(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        out=[]
        for key in sorted(a.keys()|b.keys()):
            if key not in a or key not in b:out.append(path+'/'+key+': key mismatch')
            else:out.extend(differences(a[key],b[key],path+'/'+key))
        return out
    if isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b):return [path+': length mismatch']
        return [d for i,(x,y) in enumerate(zip(a,b)) for d in differences(x,y,path+'/'+str(i))]
    return [] if a==b else [path+': '+str(a)+' -> '+str(b)]
def artifacts(result):
    out={}
    for key,value in result.items():
        if key in {'image_path','analysis_image_path'}:continue
        if key.endswith('_path') and isinstance(value,str) and value:out[key]=value
        elif key.endswith('_paths') and isinstance(value,dict):
            for code,path in value.items():
                if path:out[key+'/'+code]=path
    return out

def compare(name):
    before=json.loads((folder/'before'/f'{name}.json').read_text(encoding='utf-8-sig'))
    after=json.loads((folder/'after'/f'{name}.json').read_text(encoding='utf-8-sig'))
    diffs=differences(normalized(before),normalized(after))
    paths1,paths2=artifacts(before),artifacts(after)
    images=[]
    for key in paths1:
        with Image.open(paths1[key]) as a, Image.open(paths2[key]) as b:
            a,b=a.convert('RGB'),b.convert('RGB')
            same=a.size==b.size and ImageChops.difference(a,b).getbbox() is None
            images.append({'artifact':key,'pixels_identical':same,'size':list(a.size)})
    return {'case':name,'quality_before':before['quality'],'quality_after':after['quality'],'grade_before':before['grade'],'grade_after':after['grade'],'quality_confidence_difference':after['quality_confidence']-before['quality_confidence'],'grade_confidence_difference':after['grade_confidence']-before['grade_confidence'],'counts':after['lesion_counts'],'result_differences':diffs,'images':images,'all_equal':not diffs and all(x['pixels_identical'] for x in images)}

def main():
    cases=[f'case_{i}' for i in range(6)]+['cpu_good','cpu_usable']
    report=[compare(name) for name in cases]
    (folder/'parity.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    for row in report:print(row['case'],row['quality_after'],row['grade_after'],'exact:',row['all_equal'],'PNGs:',len(row['images']),'differences:',row['result_differences'][:3])
    if not all(row['all_equal'] for row in report):raise SystemExit(1)
if __name__=='__main__':main()
