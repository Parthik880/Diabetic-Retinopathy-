const fs = require('node:fs');
const path = require('node:path');
exports.runSmoke = async (window, origin, root, backendPid) => {
  const wc = window.webContents;
  const evaluate = text => wc.executeJavaScript(text, true);
  const wait = async (text, timeout = 120000) => {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      if (await evaluate(text)) return;
      await new Promise(resolve => setTimeout(resolve, 150));
    }
    throw new Error('Timeout: ' + text);
  };
  const click = async text => evaluate(`(() => { const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)} || b.innerText.trim().endsWith(${JSON.stringify(text)})); if(!b)throw new Error('Missing '+${JSON.stringify(text)}); b.click(); })()`);
  const select = async (label, value) => evaluate(`(() => {const s=document.querySelector('select[aria-label="${label}"]');s.value=${JSON.stringify(value)};s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  const snap = async name => {
    await wait("[...document.images].every(i => i.complete)");
    await evaluate('window.scrollTo(0,0)');
    await evaluate('document.fonts.ready');
    window.show();
    window.focus();
    await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
    const shot = await wc.debugger.sendCommand('Page.captureScreenshot', {format:'png', fromSurface:true, captureBeyondViewport:false});
    fs.writeFileSync(path.join(root,'work',name+'.png'), Buffer.from(shot.data,'base64'));
  };
  const checks = [];
  const errors = [];
  let analyzeCount = 0;
  wc.debugger.attach('1.3');
  await wc.debugger.sendCommand('Network.enable');
  wc.debugger.on('message',(_e,method,params)=>{ if(method==='Network.requestWillBeSent' && params.request.url.endsWith('/api/analysis-jobs')) analyzeCount++; });
  await evaluate("window.addEventListener('error', e => { window.__visualErrors = [...(window.__visualErrors||[]),e.message]; });");
  await wait("document.body.innerText.includes('Analyze Retinal Images')");
  // Existing local samples are distinct real retinal images. Analyze both via UI.
  await click('Analyze Retinal Images');
  await wait("document.body.innerText.includes('Eye 2 of 2') && document.body.innerText.includes('Analysis complete')", 180000);
  await click('Report');
  await wait("document.body.innerText.includes('Diabetic Retinopathy') && document.body.innerText.includes('Left (OS)')");
  await evaluate("[...document.querySelectorAll('[role=tab]')].find(b => b.textContent.startsWith('Right Eye (OD)')).click()");
  await wait("document.body.innerText.includes('Analysis in progress') && ['Assessing image quality','Image quality: Good','Image quality: Usable','Restoring usable retinal image','Restoration complete','Classifying diabetic retinopathy grade','Analyzing retinal lesions','Preparing results'].some(stage => document.body.innerText.includes(stage))");
  checks.push('Completed-eye report remains available while the other eye shows its real live stage');
  await click('Capture');
  await wait("document.body.innerText.includes('Retinal Analysis Complete')", 180000);
  await click('Analysis');
  await wait("document.querySelector('[data-testid=visualization-OS]')?.dataset.runId");
  const osRun = await evaluate("document.querySelector('[data-testid=visualization-OS]').dataset.runId");
  await click('OD (Right)');
  await wait("document.querySelector('[data-testid=visualization-OD]')?.dataset.runId");
  const odRun = await evaluate("document.querySelector('[data-testid=visualization-OD]').dataset.runId");
  if (osRun === odRun) throw new Error('Both eyes reused one run');
  const os = await (await fetch(`${origin}/artifacts/${osRun}/response.json`)).json();
  const od = await (await fetch(`${origin}/artifacts/${odRun}/response.json`)).json();
  if (os.eye !== 'OS' || od.eye !== 'OD') throw new Error('Eye API metadata mismatch');
  await click('OS (Left)');
  await wait("document.querySelector('[data-testid=visualization-OS]')?.dataset.runId");
  for (const [key,title] of Object.entries({grade:'Grade Analysis',attention:'Lesion Grad-CAM',detection:'Lesion Detection',annotation:'Lesion Annotation'})) {
    await click(title);
    await wait(`document.querySelector('[data-testid=visualization-OS]')?.dataset.view==='${key}'`);
    if(key==='grade' || key==='attention') {
      await wait("document.querySelector('[data-testid=attention-layer-OS]')?.naturalWidth>0");
      const src=await evaluate("document.querySelector('[data-testid=attention-layer-OS]').src");
      if(!src.includes(osRun)) throw new Error('Wrong OS attention run');
    }
    if(key==='detection') {
      await require('./topk-checks.cjs').check({evaluate,wait,select,click,os,origin,root});
      const ids = () => evaluate("[...document.querySelectorAll('[data-testid=visualization-OS] [data-region-id]')].map(e=>e.dataset.regionId)");
      const boxesIds = await ids();
      if(boxesIds.length!==Math.min(25,os.lesions.displayed_region_count)) throw new Error('Boxes do not use Top 25 retained regions');
      await click('Coordinates');
      if(JSON.stringify(await ids())!==JSON.stringify(boxesIds)) throw new Error('Coordinates uses different region IDs');
      await evaluate("document.querySelector('input[aria-label=\"View all raw model regions\"]').click()");
      await wait(`document.querySelectorAll('[data-testid=visualization-OS] [data-region-id]').length===${os.lesions.raw_region_count}`);
      await snap('visual-raw-regions');
      await evaluate("document.querySelector('input[aria-label=\"View all raw model regions\"]').click()");
      await wait(`document.querySelectorAll('[data-testid=visualization-OS] [data-region-id]').length===${Math.min(25,os.lesions.displayed_region_count)}`);
      checks.push('Filtered boxes by default, full raw toggle, identical Boxes/Coordinates IDs');
      await evaluate("document.querySelector('[data-region-id]').dispatchEvent(new MouseEvent('click',{bubbles:true}))");
      const firstId=(await ids())[0].split('-');
      const region=os.lesions.lesions[firstId[1]].regions.find(r=>r.region_id===Number(firstId[2]));
      const details=await evaluate("document.querySelector('[data-testid=region-details-OS]').textContent");
      if(!details.includes(`X2: ${region.x_max}`) || !details.includes(`Y: ${region.center_y}`)) throw new Error('Original region coordinates differ');
      await evaluate("(() => {const p=document.querySelector('[data-testid=image-plane-OS]');const r=p.getBoundingClientRect();p.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,clientX:r.left+r.width/2,clientY:r.top+r.height/2}));})()");
      await wait(`document.querySelector('[data-testid=cursor-OS]').textContent.includes('X: ${Math.floor(os.image_width/2)}')`);
      checks.push('Original-pixel boxes, centers, and pointer conversion');
    }
    if(key==='annotation') {
      await wait("document.querySelector('[data-testid=mask-layer-OS-MA]')?.naturalWidth>0");
      await click('Mask'); await click('Original'); await click('Overlay');
      checks.push('Annotation original / mask / overlay modes');
    }
    await snap(`visual-analysis-${key}`);
    await click('OD (Right)');
    await wait(`document.querySelector('[data-testid=visualization-OD]')?.dataset.view==='${key}'`);
    const run=await evaluate("document.querySelector('[data-testid=visualization-OD]').dataset.runId");
    if(run!==odRun) throw new Error('Eye switch lost OD result');
    const sources=await evaluate("[...document.querySelectorAll('[data-testid=visualization-OD] img')].map(i=>i.src)");
    if(sources.some(src=>src.includes(osRun))) throw new Error('OS layer leaked into OD view');
    await click('OS (Left)');
    await wait("document.querySelector('[data-testid=visualization-OS]') !== null");
  }
  checks.push('Four Analysis views, real layers, independent OS/OD cached results');
  await click('Grade Analysis');
  await click('Confirm Diagnosis');
  await click('OD (Right)');
  if(await evaluate("document.body.textContent.includes('Diagnosis Confirmed')"))throw new Error('OS confirmation leaked to OD');
  checks.push('Eye-specific diagnosis controls');
  await click('Compare');
  await wait("document.querySelector('[data-testid=bilateral-panels]') !== null");
  for(const mode of ['grade','attention','detection','annotation']) {
    await select('Comparison View',mode);
    await wait(`document.querySelector('[data-testid=visualization-OS]')?.dataset.view==='${mode}' && document.querySelector('[data-testid=visualization-OD]')?.dataset.view==='${mode}'`);
    if(mode==='grade') {
      const grades=await evaluate("['OS','OD'].map(e=>document.querySelector('[data-testid=compare-grade-'+e+']').textContent)");
      if(+grades[0]!==os.grading.predicted_grade || +grades[1]!==od.grading.predicted_grade) throw new Error('Bilateral grade mismatch');
    }
    await snap(`visual-compare-${mode}`);
  }
  const size=await evaluate("['OS','OD'].map(e=>{const r=document.querySelector('[data-testid=image-stage-'+e+']').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};})");
  if(Math.abs(size[0].width-size[1].width)>1 || size[0].x>=size[1].x)throw new Error('Desktop bilateral panel dimensions/order failed');
  checks.push('Synchronized Compare modes, correct grade ownership, matching desktop panels');
  await click('Report');
  await wait("document.querySelector('[data-testid=report-region-appendix]')!==null");
  const tableSizes = await evaluate("['report-top-regions','report-region-appendix'].map(id=>document.querySelector('[data-testid='+id+']').querySelectorAll('tbody tr').length)");
  if(tableSizes[0]!==Math.min(25,od.lesions.displayed_region_count) || tableSizes[1]!==od.lesions.displayed_region_count) throw new Error('Report region tables incorrect');
  for(const k of ['5','10','25','50','all']) {
    await select('Report regions shown',k);
    const count=k==='all'?od.lesions.displayed_region_count:Math.min(+k,od.lesions.displayed_region_count);
    await wait(`document.querySelector('[data-testid=report-top-regions]').querySelectorAll('tbody tr').length===${count}`);
    if(!(await evaluate("document.querySelector('[data-testid=report-selection-summary]').textContent")).includes(`Showing ${count} of ${od.lesions.displayed_region_count}`))throw new Error('Report Top-K wording incorrect');
    if(await evaluate("document.querySelector('[data-testid=report-region-appendix]').querySelectorAll('tbody tr').length")!==od.lesions.displayed_region_count)throw new Error('Report appendix was truncated');
  }
  await select('Report regions shown','25');
  await snap('visual-postprocessing-report');
  fs.writeFileSync(path.join(root,'work/postprocessing-report.pdf'), await wc.printToPDF({pageSize:'A4',printBackground:true}));
  checks.push('Report Top-K selector and count wording; full retained-region appendix; PDF exported');
  await click('Compare');
  await wait("document.querySelector('[data-testid=bilateral-panels]')!==null");
  await wc.debugger.sendCommand('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await new Promise(resolve=>setTimeout(resolve,250));
  await snap('visual-compare-mobile');
  const narrow=await evaluate("({overflow:document.documentElement.scrollWidth>innerWidth+1,panels:['OS','OD'].map(e=>document.querySelector('[data-testid=image-stage-'+e+']').getBoundingClientRect().y)})");
  if(narrow.overflow || narrow.panels[0]>=narrow.panels[1]) throw new Error('Narrow Compare layout failed');
  await click('Analysis');
  await click('Lesion Annotation');
  await snap('visual-analysis-mobile');
  if(await evaluate('document.documentElement.scrollWidth>innerWidth+1'))throw new Error('Narrow Analysis overflow');
  checks.push('390px responsive Analysis and stacked Compare');
  await wc.debugger.sendCommand('Emulation.clearDeviceMetricsOverride');
  if(analyzeCount!==2)throw new Error(`Tab switches triggered inference: ${analyzeCount}`);
  checks.push('Exactly two inference requests for two eyes; no requests on view changes');
  errors.push(...await evaluate('window.__visualErrors||[]'));
  if(errors.length) throw new Error(errors.join('\n'));
  fs.writeFileSync(path.join(root,'work/visual-smoke.json'),JSON.stringify({osRun,odRun,osGrade:os.grading.predicted_grade,odGrade:od.grading.predicted_grade,osRegions:os.lesions.postprocessing.statistics,odRegions:od.lesions.postprocessing.statistics,backendPid,checks,errors,analyzeCount},null,2));
  wc.debugger.detach();
};
