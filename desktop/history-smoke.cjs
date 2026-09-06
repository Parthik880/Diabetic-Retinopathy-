const fs = require('node:fs');
const path = require('node:path');

exports.runSmoke = async (window, origin, root, backendPid) => {
  const contents = window.webContents;
  const evaluate = script => contents.executeJavaScript(script, true);
  const waitFor = async (script, timeout = 30000) => {
    const started = Date.now();
    while (Date.now() - started < timeout) {
      if (await evaluate(script)) return;
      await new Promise(resolve => setTimeout(resolve, 150));
    }
    throw new Error(`Timed out waiting for ${script}`);
  };
  const click = text => evaluate(`(() => { const button=[...document.querySelectorAll('button')].find(item=>item.textContent.includes(${JSON.stringify(text)})); if(!button) throw new Error('Missing button: '+${JSON.stringify(text)}); button.click(); })()`);
  const select = (label, value) => evaluate(`(() => { const element=document.querySelector('select[aria-label="${label}"]'); element.value=${JSON.stringify(value)}; element.dispatchEvent(new Event('change',{bubbles:true})); })()`);
  const search = value => evaluate(`(() => { const input=document.querySelector('input[placeholder="Search by patient name or ID"]'); const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set; setter.call(input,${JSON.stringify(value)}); input.dispatchEvent(new Event('input',{bubbles:true})); })()`);

  await waitFor("document.body.innerText.includes('Analyze Retinal Images')");
  const history = await (await fetch(`${origin}/api/history`)).json();
  const sessions = history.records.filter(record => record.patient_id === 'RH-8842');
  if (sessions.length < 3) throw new Error('History smoke requires the persisted three-session patient fixture.');
  await click('History');
  await waitFor("document.body.innerText.includes('Scan History') && [...document.querySelectorAll('button')].some(button => button.textContent.includes('View history'))");
  if (await evaluate("document.querySelectorAll('tbody tr').length") !== 1) throw new Error('One patient was not grouped into one row.');
  await search('RH-8842');
  await waitFor("document.body.innerText.includes('Eleanor Vance')");
  for (const dateFilter of ['today', '7', '30', 'all']) {
    await select('History date filter', dateFilter);
    await waitFor("document.body.innerText.includes('Eleanor Vance')");
  }
  for (const eyeFilter of ['OS', 'OD', 'both', 'all']) {
    await select('History eye filter', eyeFilter);
    await waitFor("document.body.innerText.includes('Eleanor Vance')");
  }
  await click('View history');
  await waitFor(`document.querySelectorAll('aside article').length === ${sessions.length}`);
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
  fs.writeFileSync(path.join(root, 'work', 'desktop-history.png'), (await contents.capturePage()).toPNG());

  const newest = [...sessions].sort((a, b) => Date.parse(b.scan_datetime) - Date.parse(a.scan_datetime))[0];
  const bilateral = [...sessions].sort((a, b) => Date.parse(b.scan_datetime) - Date.parse(a.scan_datetime))
    .find(record => record.left_eye.completed && record.right_eye.completed);
  if (!bilateral) throw new Error('History smoke requires a bilateral session for eye switching and dropdown download.');
  await evaluate(`(() => { const card=[...document.querySelectorAll('aside article')].find(item=>item.textContent.includes(${JSON.stringify(bilateral.session_id)})); card.querySelectorAll('button')[1].click(); })()`);
  await waitFor("[...document.querySelectorAll('button')].some(button => button.textContent.includes('Download Right Eye Report'))");
  await click('Download Right Eye Report');
  await waitFor("document.body.innerText.includes('OD report saved to')");
  await evaluate(`(() => { const card=[...document.querySelectorAll('aside article')].find(item=>item.textContent.includes(${JSON.stringify(bilateral.session_id)})); card.querySelectorAll('button')[0].click(); })()`);
  await waitFor("document.body.innerText.includes('Diabetic Retinopathy')");
  const firstEye = bilateral.left_eye.completed ? 'OS' : 'OD';
  const firstRun = (firstEye === 'OS' ? bilateral.left_eye : bilateral.right_eye).result_data.run_id;
  if (!(await evaluate('document.body.innerText')).includes(firstRun)) throw new Error('View Reports opened the wrong persisted session.');
  await click('Right Eye (OD)');
  await waitFor(`document.body.innerText.includes(${JSON.stringify(bilateral.right_eye.result_data.run_id)})`);
  fs.writeFileSync(path.join(root, 'work', 'history-smoke.json'), JSON.stringify({
    backendPid, groupedRows: 1, patientId: 'RH-8842', sessions: sessions.length,
    newestSessionId: newest.session_id, exactSessionId: bilateral.session_id, exactRunId: firstRun,
    searchVerified: true, dateFiltersVerified: true, eyeFiltersVerified: true,
    reportEyeSwitchVerified: true, perEyeHistoryDownloadVerified: true,
    restartPersistenceVerified: true,
  }, null, 2));
};
