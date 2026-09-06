const fs = require('node:fs');
const path = require('node:path');

exports.runSmoke = async (window, origin, root, backendPid) => {
  const contents = window.webContents;
  const errors = [];
  const historyPath = path.join(root, 'work', 'smoke-profile', 'retinagram-history.json');
  const priorHistory = fs.existsSync(historyPath) ? JSON.parse(fs.readFileSync(historyPath, 'utf8')) : [];
  const priorSessionIds = priorHistory.map(record => record.session_id);
  contents.on('console-message', event => { if (event.level === 'error') errors.push(event.message); });
  const evaluate = script => contents.executeJavaScript(script, true);
  const waitFor = async (script, timeout = 30000) => {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      if (await evaluate(script)) return;
      await new Promise(resolve => setTimeout(resolve, 200));
    }
    throw new Error(`Timed out waiting for ${script}`);
  };
  const click = async text => {
    await evaluate(`(() => { const button = [...document.querySelectorAll('button')].find(b => b.textContent.includes(${JSON.stringify(text)})); if (!button) throw new Error('Missing button: ' + ${JSON.stringify(text)}); button.click(); })()`);
  };
  const select = async (label, value) => evaluate(`(() => { const element = document.querySelector('select[aria-label="${label}"]'); if (!element) throw new Error('Missing select: ${label}'); element.value = ${JSON.stringify(value)}; element.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  const searchHistory = async value => evaluate(`(() => { const input = document.querySelector('input[placeholder="Search by patient name or ID"]'); if (!input) throw new Error('Missing history search'); const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; setter.call(input, ${JSON.stringify(value)}); input.dispatchEvent(new Event('input', { bubbles: true })); })()`);
  await waitFor("document.body.innerText.includes('Analyze Retinal Images')");
  await click('Retake / Replace Image');
  await waitFor("document.querySelector('input[type=file]') !== null");
  contents.debugger.attach('1.3');
  const upload = async file => {
    const { root: document } = await contents.debugger.sendCommand('DOM.getDocument');
    const { nodeId } = await contents.debugger.sendCommand('DOM.querySelector', { nodeId: document.nodeId, selector: 'input[type=file]' });
    await contents.debugger.sendCommand('DOM.setFileInputFiles', { nodeId, files: [file] });
  };
  const selectFile = async file => {
    await click('Retake / Replace Image');
    await waitFor("document.querySelector('input[type=file]') !== null");
    await upload(file);
    await waitFor("[...document.querySelectorAll('button')].some(b => b.textContent.includes('Apply Scan'))");
    await click('Apply Scan');
  };
  await upload(path.join(root, 'resources/test-images/20170629163635747.jpg'));
  await waitFor("[...document.querySelectorAll('button')].some(b => b.textContent.includes('Apply Scan') && !b.disabled)");
  await click('Apply Scan');
  await click('Analyze Retinal Images');
  await waitFor("document.body.innerText.includes('Retinal Analysis Complete')", 180000);
  await click('Analysis');
  await waitFor("document.querySelector('[data-testid=model-result]')?.textContent.includes('Inference run:')", 120000);
  const displayed = await evaluate("document.body.innerText");
  if (!displayed.includes('IQA: Good') || !displayed.includes('DR grade 3') || !displayed.includes('92.2%')) {
    throw new Error('Expected real model results were not displayed. ' + displayed.slice(0, 2500));
  }
  const resultText = await evaluate("document.querySelector('[data-testid=model-result]').innerText");
  fs.writeFileSync(path.join(root, 'work', 'desktop-analysis.png'), (await contents.capturePage()).toPNG());
  await click('Report');
  await waitFor("[...document.querySelectorAll('button')].some(b => b.textContent.includes('Report') && b.getAttribute('aria-current') === 'page') && document.body.textContent.includes('Diabetic Retinopathy')");
  await new Promise(resolve => setTimeout(resolve, 300));
  const report = await evaluate('document.body.innerText');
  if (report.includes('94% algorithmic confidence') || report.includes('Moderate Nonproliferative')) throw new Error('Static diagnostic report survived in tested path.');
  if (report.includes('Grad-CAM')) throw new Error('Grad-CAM appeared in the standard report.');
  fs.writeFileSync(path.join(root, 'work', 'desktop-report.png'), (await contents.capturePage()).toPNG());
  await click('Save Left Eye Report');
  await waitFor("document.body.textContent.includes('Report saved to')", 30000);
  const exportRoot = path.join(root, 'work', 'test-report-exports');
  const reportFolder = fs.readdirSync(exportRoot, { withFileTypes: true })
    .filter(entry => entry.isDirectory() && entry.name.startsWith('RetinaGram_'))
    .map(entry => path.join(exportRoot, entry.name))
    .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
  for (const required of ['Left_OS/report.pdf', 'Left_OS/original_fundus.jpg', 'Left_OS/lesion_overlay.png', 'Left_OS/results.json']) {
    if (!reportFolder || !fs.existsSync(path.join(reportFolder, required))) throw new Error(`Missing report export: ${required}`);
  }

  // Real persisted History: search by both fields, exercise every eye/date filter,
  // reopen the bilateral record, switch eyes, and export the selected Right eye.
  await click('History');
  await waitFor("document.body.innerText.includes('Scan History') && document.body.innerText.includes('Eleanor Vance')", 30000);
  const persistedHistory = await (await fetch(`${origin}/api/history`)).json();
  if (!priorSessionIds.every(id => persistedHistory.records.some(record => record.session_id === id))) {
    throw new Error('A history session from the previous app run did not survive restart.');
  }
  const patientSessions = persistedHistory.records.filter(record => record.patient_id === 'RH-8842');
  if (await evaluate("document.querySelectorAll('tbody tr').length") !== 1) throw new Error('History did not group one patient into one row.');
  await searchHistory('Eleanor');
  await waitFor("document.body.innerText.includes('Eleanor Vance')");
  await searchHistory('RH-8842');
  await waitFor("document.body.innerText.includes('Eleanor Vance')");
  await select('History date filter', 'today');
  await waitFor("document.body.innerText.includes('Eleanor Vance')");
  for (const eyeFilter of ['OS', 'OD', 'both']) {
    await select('History eye filter', eyeFilter);
    await waitFor("document.body.innerText.includes('Eleanor Vance') && [...document.querySelectorAll('button')].some(b => b.textContent.includes('View history'))");
  }
  await click('View history');
  await waitFor(`document.querySelectorAll('aside article').length === ${patientSessions.length}`);
  fs.writeFileSync(path.join(root, 'work', 'desktop-history.png'), (await contents.capturePage()).toPNG());
  await click('Download');
  await waitFor("[...document.querySelectorAll('button')].some(b => b.textContent.includes('Download Right Eye Report'))");
  await click('Download Right Eye Report');
  await waitFor("document.body.textContent.includes('OD report saved to')", 30000);
  await click('View Reports');
  await waitFor("document.body.innerText.includes('Diabetic Retinopathy') && document.body.innerText.includes('Left (OS)')");
  await click('Right Eye (OD)');
  await waitFor("document.body.innerText.includes('Right (OD)') && [...document.querySelectorAll('button')].some(b => b.textContent.includes('Save Right Eye Report'))");
  const latestSession = [...patientSessions].sort((a, b) => Date.parse(b.scan_datetime) - Date.parse(a.scan_datetime))[0];
  if (!latestSession.right_eye.result_data?.run_id || !(await evaluate('document.body.innerText')).includes(latestSession.right_eye.result_data.run_id)) {
    throw new Error('History opened the wrong session result.');
  }
  const rightReportFolder = fs.readdirSync(exportRoot, { withFileTypes: true })
    .filter(entry => entry.isDirectory() && entry.name.startsWith('RetinaGram_'))
    .map(entry => path.join(exportRoot, entry.name))
    .filter(entry => entry !== reportFolder)
    .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
  for (const required of ['Right_OD/report.pdf', 'Right_OD/original_fundus.jpg', 'Right_OD/lesion_overlay.png', 'Right_OD/results.json']) {
    if (!rightReportFolder || !fs.existsSync(path.join(rightReportFolder, required))) throw new Error(`Missing Right report export: ${required}`);
  }
  if (fs.existsSync(path.join(rightReportFolder, 'Left_OS'))) throw new Error('Right-only export created an empty Left_OS folder.');
  await click('Analysis');
  await waitFor("document.body.innerText.includes('OS (Left)')");
  await click('OD (Right)');
  await waitFor("document.body.innerText.includes('Inference run:')");
  await click('OS (Left)');
  await waitFor("document.body.innerText.includes('DR grade 3')");
  // Checkpoint-backed USABLE renderer path: live state polling, restored image,
  // and terminal result all reach the actual Electron UI.
  await click('Capture');
  await selectFile(path.join(root, 'work', 'routing-test-inputs', 'usable.png'));
  await click('Analyze Retinal Images');
  await waitFor("document.body.innerText.includes('Retinal Analysis Complete')", 120000);
  await click('Analysis');
  await waitFor("document.querySelector('[data-testid=model-result]')?.textContent.includes('State COMPLETE')", 120000);
  const usableText = await evaluate("document.querySelector('[data-testid=model-result]').innerText");
  if (!usableText.includes('IQA: Usable') || !usableText.includes('NAFNet-restored image')) throw new Error('USABLE route did not reach the renderer: ' + usableText);
  await click('Report');
  await waitFor("document.body.innerText.toLowerCase().includes('nafnet restored image')");
  // Checkpoint-backed RECAPTURE renderer path: terminal UI, no downstream model result.
  await click('Capture');
  await selectFile(path.join(root, 'work', 'routing-test-inputs', 'recapture.png'));
  await click('Analyze Retinal Images');
  await waitFor("document.body.innerText.includes('Recapture required')", 120000);
  await click('Analysis');
  await waitFor("document.querySelector('[data-testid=model-result]')?.textContent.includes('State RECAPTURE_REQUIRED')", 120000);
  const recaptureText = await evaluate("document.body.innerText");
  if (!recaptureText.includes('Recapture required') || !recaptureText.includes('grading, and lesion analysis were intentionally skipped')) throw new Error('RECAPTURE route did not reach terminal renderer UI.');
  // Negative UI tests are isolated from the successful real-model run above.
  const failureChecks = [];
  await click('Capture');
  const bad = path.join(root, 'work', 'invalid-test.jpg');
  fs.writeFileSync(bad, 'deliberately invalid image for negative integration test');
  await selectFile(bad);
  await click('Analyze Retinal Images');
  await waitFor("document.querySelector('[role=alert]')?.textContent.includes('Invalid or unreadable')");
  failureChecks.push('invalid image error from real backend');
  const gif = path.join(root, 'work', 'unsupported-test.gif');
  fs.writeFileSync(gif, Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7', 'base64'));
  await selectFile(gif);
  await click('Analyze Retinal Images');
  await waitFor("document.querySelector('[role=alert]')?.textContent.includes('Unsupported format')");
  failureChecks.push('unsupported format error from real backend');
  await selectFile(path.join(root, 'resources/test-images/20170629163635747.jpg'));
  let failureMode = 'offline';
  const intercept = (_event, method, params) => {
    if (method !== 'Fetch.requestPaused') return;
    if (failureMode === 'offline') {
      contents.debugger.sendCommand('Fetch.failRequest', { requestId: params.requestId, errorReason: 'ConnectionFailed' });
    } else {
      contents.debugger.sendCommand('Fetch.fulfillRequest', { requestId: params.requestId, responseCode: 500,
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
        body: Buffer.from(JSON.stringify({ detail: 'Inference failed (negative UI test).' })).toString('base64') });
    }
  };
  contents.debugger.on('message', intercept);
  await contents.debugger.sendCommand('Fetch.enable', { patterns: [{ urlPattern: '*/api/analysis-jobs', requestStage: 'Request' }] });
  await click('Analyze Retinal Images');
  await waitFor("document.querySelector('[role=alert]')?.textContent.includes('Local backend unavailable')");
  failureChecks.push('backend disconnected renderer error (network fault injection)');
  failureMode = 'inference';
  await click('Analyze Retinal Images');
  await waitFor("document.querySelector('[role=alert]')?.textContent.includes('Inference failed')");
  failureChecks.push('inference 500 renderer error (failure response injection)');
  await contents.debugger.sendCommand('Fetch.disable');
  contents.debugger.off('message', intercept);
  contents.debugger.detach();
  fs.writeFileSync(path.join(root, 'work', 'desktop-smoke.json'), JSON.stringify({
    origin, backendPid, resultText, reportVerified: true, reportFolder, rightReportFolder, perEyeIsolation: true,
    historyVerified: 'restart persistence, one grouped patient row, full session panel, name/ID search, date/OS/OD/Both filters, exact-session reopen, eye switching and per-eye download',
    priorSessionsSurvivedRestart: priorSessionIds.length,
    upload: 'Actual file input through Chromium DOM.setFileInputFiles',
    pipeline: 'Electron React UI -> queued multipart API -> single IQA routing -> optional NAFNet -> grade/lesion -> terminal renderer state',
    usableRendererVerified: true, recaptureRendererVerified: true,
    failureChecks, consoleErrorsIncludingExpectedNegativeTests: errors
  }, null, 2));
};
