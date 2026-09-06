const fs=require('node:fs');
const path=require('node:path');
exports.check = async ({evaluate,wait,select,click,os,origin,root}) => {
  const ranked=Object.entries(os.lesions.lesions).flatMap(([code,item])=>item.regions.map(r=>({...r,id:`OS-${code}-${r.region_id}`,code})))
    .sort((a,b)=>b.mean_probability-a.mean_probability || (a.id<b.id?-1:a.id>b.id?1:0));
  const ids=()=>evaluate("[...document.querySelectorAll('[data-testid=visualization-OS] [data-region-id]')].map(e=>e.dataset.regionId)");
  await click('Lesion Annotation');
  const maskBefore=await evaluate("document.querySelector('[data-testid=mask-layer-OS-MA]').src");
  await click('Lesion Detection');
  if(await evaluate("document.querySelector('select[aria-label=\"Regions shown\"]').value")!=='25')throw new Error('Top 25 is not default');
  const results=[];
  for(const k of ['5','10','20','25','50','all']) {
    await select('Regions shown',k);
    const expected=(k==='all'?ranked:ranked.slice(0,+k)).map(r=>r.id);
    await wait(`JSON.stringify([...document.querySelectorAll('[data-testid=visualization-OS] [data-region-id]')].map(e=>e.dataset.regionId))===${JSON.stringify(JSON.stringify(expected))}`);
    await click('Boxes'); const boxes=await ids();
    await click('Coordinates'); const coords=await ids();
    if(JSON.stringify(boxes)!==JSON.stringify(coords))throw new Error('Top-K Boxes/Coordinates mismatch');
    results.push({k,count:boxes.length});
  }
  await select('Region class','EX'); await select('Regions shown','50');
  await wait(`document.querySelectorAll('[data-testid=visualization-OS] [data-region-id]').length===${os.lesions.lesions.EX.regions.length}`);
  const limited=await ids();
  if(limited.some(id=>!id.startsWith('OS-EX-')))throw new Error('Class filter not applied first');
  await select('Region class','all');await select('Regions shown','25');
  await click('Lesion Annotation');
  if(await evaluate("document.querySelector('[data-testid=mask-layer-OS-MA]').src")!==maskBefore)throw new Error('Top-K replaced full mask layer');
  const response=await (await fetch(`${origin}/artifacts/${os.run_id}/response.json`)).json();
  if(response.lesions.raw_region_count!==os.lesions.raw_region_count || response.lesions.displayed_region_count!==os.lesions.displayed_region_count) throw new Error('Top-K changed backend counts');
  await click('Lesion Detection');
  fs.writeFileSync(path.join(root,'work/topk-test.json'),JSON.stringify({run:os.run_id,raw:os.lesions.raw_region_count,filtered:os.lesions.displayed_region_count,topK:25,displayed:Math.min(25,ranked.length),lowestDisplayedMeanProbability:ranked[Math.min(25,ranked.length)-1]?.mean_probability,options:results,undersupplyClass:'EX',undersupplyDisplayed:limited.length,checks:['exact mean-probability ranking','stable identical IDs in Boxes and Coordinates','class filter before Top-K','K above available count','unchanged full mask URL','unchanged raw/filtered backend counts']},null,2));
};
