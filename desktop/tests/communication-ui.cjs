// Run with Electron. All generated data is isolated under work; no OS apps launch.
const { app, BrowserWindow, ipcMain, clipboard } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const assert = require('node:assert/strict');
const { openCommunication } = require('../communication.cjs');
const root = path.resolve(__dirname, '../..');
const work = path.join(root, 'work', `communication-qa-${Date.now()}`);
fs.mkdirSync(work, { recursive: true });
app.setPath('userData', path.join(work, 'profile'));
let backend, window;
let failHandler = false, cancelFolder = false;
const launched = [];
const checks = [];
const patientCode = 'RH-COMM-' + Date.now();
const check = (name, condition = true) => { assert.ok(condition, name); checks.push(name); };
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

app.whenReady().then(async () => {
  const port = await new Promise(resolve => {
    const socket = net.createServer().listen(0, '127.0.0.1', () => { const port = socket.address().port; socket.close(() => resolve(port)); });
  });
  const origin = `http://127.0.0.1:${port}`;
  const log = fs.openSync(path.join(work, 'backend.log'), 'a');
  backend = spawn(process.env.RETINA_PYTHON || 'python', [path.join(__dirname, 'fixture_server.py'), String(port)], {
    cwd: root, windowsHide: true, stdio: ['ignore', log, log],
    env: { ...process.env, PYTHONPATH: [path.join(root, 'work/qa-python'), path.join(root, 'backend')].join(path.delimiter),
      PYTHONDONTWRITEBYTECODE: '1', MPLCONFIGDIR: path.join(work, 'matplotlib'),
      RETINA_RUNTIME_ROOT: work, RETINA_HISTORY_PATH: path.join(work, 'history.json') },
  });
  fs.closeSync(log);
  for (let count = 0; count < 100; count++) {
    try { if ((await fetch(`${origin}/health`)).ok) break; } catch {}
    if (backend.exitCode !== null) throw new Error('Fixture backend exited; inspect ' + work);
    await pause(300);
  }
  ipcMain.handle('retinagram:choose-report-folder', () => cancelFolder ? null : work);
  ipcMain.handle('retinagram:copy-text', async (_event, value) => { await clipboard.writeText(value); return { copied: true }; });
  ipcMain.handle('retinagram:communicate', (_event, request) => openCommunication(request, {
    openExternal: async url => { if (failHandler) throw new Error('No handler'); launched.push(url); },
  }));
  window = new BrowserWindow({ show: false, width: 1440, height: 1000, webPreferences: {
    preload: path.join(root, 'desktop/preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true,
  }});
  const wc = window.webContents;
  const errors = [];
  wc.on('console-message', event => { if (event.level === 'error') errors.push(event.message); });
  const evaluate = async script => {
    try { return await wc.executeJavaScript(script, true); }
    catch (error) { console.error('Failed script:', script); throw error; }
  };
  const wait = async script => {
    for (let i = 0; i < 120; i++) { if (await evaluate(script)) return; await pause(100); }
    console.error('UI at timeout:', await evaluate('document.body.innerText'), errors);
    throw new Error('Timed out: ' + script);
  };
  const click = text => evaluate(`(() => { const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)} || b.textContent.includes(${JSON.stringify(text)})); if(!b) throw new Error('No button '+${JSON.stringify(text)}); b.focus(); b.click(); })()`);
  const fill = (selector, value) => evaluate(`(() => { const input=document.querySelector(${JSON.stringify(selector)}); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,${JSON.stringify(value)}); input.dispatchEvent(new Event('input',{bubbles:true})); })()`);
  const body = text => `document.body.innerText.includes(${JSON.stringify(text)})`;
  const dialogText = text => `document.querySelector('dialog')?.innerText.includes(${JSON.stringify(text)})`;
  await window.loadURL(origin);
  await wait("document.body.innerText.includes('Register patient') || document.body.innerText.includes('New Patient')");
  await evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Register patient') || b.textContent.includes('New Patient')).click()");
  await fill('input[aria-label="Full name"]', 'Test Patient');
  await fill('input[aria-label="Patient ID"]', patientCode);
  await fill('input[type=tel]', '+91 (98765) 43210');
  await fill('input[type=email]', 'test@example.com');
  await click('Register & Begin Screening');
  await wait(body('registered successfully'));
  check('registration saves required contacts');
  await window.loadURL(origin);
  await wait(body('Test Patient'));
  const registered = (await (await fetch(`${origin}/api/patients`)).json()).patients[0];
  check('reload restores patient from PostgreSQL', registered.phone === '+919876543210' && registered.email === 'test@example.com');
  check('global header omits patient/session actions', !(await evaluate("document.querySelector('header').innerText")).match(/New [Pp]atient|New [Ss]ession/));
  check('Capture retains both actions', (await evaluate('document.body.innerText')).includes('New Session') && (await evaluate('document.body.innerText')).includes('New Patient'));
  await click('Tap to Capture Image');
  await wait("document.querySelector('input[type=file]') !== null");
  wc.debugger.attach('1.3');
  const dom = await wc.debugger.sendCommand('DOM.getDocument');
  const { nodeId } = await wc.debugger.sendCommand('DOM.querySelector', { nodeId: dom.root.nodeId, selector: 'input[type=file]' });
  await wc.debugger.sendCommand('DOM.setFileInputFiles', { nodeId, files: [path.join(root, 'resources/test-images/20170629163635747.jpg')] });
  await wait(body('Apply Scan'));
  await click('Apply Scan');
  await click('Analyze Retinal Images');
  await wait(body('Analysis complete'));
  await evaluate("document.querySelector('nav[aria-label=\"Primary navigation\"] button:nth-child(4)').click()");
  await wait(body('Send Report'));
  check('capture upload and synthetic analysis job reach Report');
  await click('Send Report');
  await wait(dialogText('test@example.com'));
  check('dialog shows selected patient contact', await evaluate(dialogText('+919876543210')));
  await click('Send via SMS');
  await wait(dialogText('Message copied.'));
  check('SMS copies message, does not claim delivery', (await clipboard.readText()).includes(patientCode));
  cancelFolder = true;
  await click('Send via Email');
  await wait(dialogText('Export cancelled.'));
  check('cancelled export does not open mail', launched.length === 0);
  cancelFolder = false;
  await click('Send via Email');
  await wait(dialogText('Email app requested.'));
  check('email uses strict encoded mailto', new URL(launched[0]).protocol === 'mailto:' && decodeURIComponent(new URL(launched[0]).pathname) === 'test@example.com');
  const savedHistory = (await (await fetch(`${origin}/api/history`)).json()).records[0];
  const pdfPath = savedHistory.left_eye.report_path;
  check('real PDF export saved and displayed', fs.readFileSync(pdfPath).subarray(0, 4).toString() === '%PDF' && await evaluate(dialogText(pdfPath)));
  check('history stores contacts', savedHistory.patient.email === 'test@example.com' && savedHistory.patient.phone === '+919876543210');
  await click('Inform via Call');
  await wait(dialogText('Call app requested.'));
  check('call invokes tel only', launched.at(-1) === 'tel:+919876543210');
  failHandler = true;
  await click('Inform via Call');
  await wait(dialogText('No calling app could be opened.'));
  await click('Copy number');
  await wait(dialogText('Number copied.'));
  check('failed call has working copy fallback', (await clipboard.readText()) === '+919876543210');
  await click('Send via Email');
  await wait(dialogText('Windows could not open an email app.'));
  check('email handler failure retains PDF instructions', await evaluate(dialogText('Saved PDF')));
  fs.writeFileSync(path.join(work, 'send-report.png'), (await wc.capturePage()).toPNG());
  await evaluate("document.querySelector('button[aria-label=\"Close send report\"]').click()");
  await wait("!document.querySelector('dialog')");
  check('dialog close restores focus', await evaluate("document.activeElement.textContent.includes('Send Report')"));
  await click('Cloud Sync');
  await wait(body('Sync overview'));
  const cloud = await (await fetch(`${origin}/api/sync`)).json();
  check('Cloud Sync reads real PostgreSQL counts', cloud.counts.patients >= 1 && cloud.counts.reports >= 1);
  check('No configured cloud cannot sync', await evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Sync now').disabled"));
  await click('Connect Cloud');
  await wait(body('Cloud provider is not configured yet.'));
  await wait("[...document.querySelectorAll('button')].some(b=>b.textContent.includes('Connect Cloud') && !b.disabled)");
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
  fs.writeFileSync(path.join(work, 'cloud-sync.png'), (await wc.capturePage()).toPNG());
  await click('Clear local data…');
  await wait("document.querySelector('dialog') !== null");
  check('cleanup defaults to no selections and disabled action', await evaluate("[...document.querySelectorAll('dialog input[type=checkbox]')].every(i=>!i.checked) && [...document.querySelectorAll('dialog button')].find(b=>b.textContent==='Clear selected data').disabled"));
  fs.writeFileSync(path.join(work, 'clear-local-data.png'), (await wc.capturePage()).toPNG());
  await click('Cancel');

  // Existing history without contacts is still supported, including report actions.
  delete savedHistory.patient.email; delete savedHistory.patient.phone;
  savedHistory.session_id = 'legacy-communication-' + Date.now();
  savedHistory.patient.id = 'legacy-' + Date.now(); savedHistory.patient_id = 'RH-LEGACY-' + Date.now(); savedHistory.patient_name = 'Legacy Patient';
  await fetch(`${origin}/api/history/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(savedHistory) });
  await click('History');
  await wait("document.querySelector('input[placeholder=\"Search by patient name or ID\"]') !== null");
  await fill('input[placeholder="Search by patient name or ID"]', savedHistory.patient_id);
  await wait("[...document.querySelectorAll('tbody tr')].some(r=>r.textContent.includes('Legacy Patient'))");
  await evaluate("[...document.querySelectorAll('tbody tr')].find(r=>r.textContent.includes('Legacy Patient')).querySelector('button').click()");
  await wait(body('View Reports'));
  await click('View Reports');
  await wait(body('Send Report'));
  await click('Send Report');
  await wait(dialogText('No email registered'));
  check('old history and missing contacts load safely', await evaluate("[...document.querySelectorAll('dialog section button')].every(b=>b.disabled)"));
  fs.writeFileSync(path.join(work, 'missing-contacts.png'), (await wc.capturePage()).toPNG());
  check('no renderer console errors', errors.length === 0);
  fs.writeFileSync(path.join(work, 'results.json'), JSON.stringify({ checks, errors, syntheticInference: true, externalAppsMocked: true, pdfPath }, null, 2));
  console.log(JSON.stringify({ work, checks }, null, 2));
}).catch(error => { console.error(error); process.exitCode = 1; }).finally(() => {
  if (backend) backend.kill();
  app.exit(process.exitCode || 0);
});
