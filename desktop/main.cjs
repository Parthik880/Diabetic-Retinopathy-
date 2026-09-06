const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const { spawn } = require('node:child_process');
const { randomUUID } = require('node:crypto');
const net = require('node:net');
const path = require('node:path');
const fs = require('node:fs');

let backend;
let stopping = false;
const devRoot = path.resolve(__dirname, '..');
const instance = randomUUID();
app.setName('RetinaGram GPU');
app.setPath('userData', path.join(app.getPath('appData'), 'RetinaGram GPU'));
if (process.env.RETINA_SMOKE === '1' && !app.isPackaged) {
  app.setPath('userData', path.join(devRoot, 'work', 'smoke-profile'));
  app.commandLine.appendSwitch('disable-renderer-backgrounding');
  app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');
  app.commandLine.appendSwitch('disable-background-timer-throttling');
}

function availablePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}

async function start() {
  const runtimeRoot = path.join(app.getPath('userData'), 'runtime');
  const logs = path.join(runtimeRoot, 'logs');
  fs.mkdirSync(logs, { recursive: true });
  const python = process.env.RETINA_PYTHON || path.join(devRoot, '.venv', 'Scripts', 'python.exe');
  const devBackendRoot = path.join(devRoot, 'dist', 'RetinaGramBackend');
  const packagedBackendRoot = path.join(process.resourcesPath, 'backend', 'RetinaGramBackend');
  const backendRoot = app.isPackaged ? packagedBackendRoot : devBackendRoot;
  const packagedBackend = path.join(backendRoot, 'RetinaGramBackend.exe');
  const frontendIndex = app.isPackaged
    ? path.join(backendRoot, '_internal', 'frontend', 'dist', 'index.html')
    : path.join(devRoot, 'frontend', 'dist', 'index.html');
  const resourceRoot = app.isPackaged
    ? path.join(backendRoot, '_internal', 'resources')
    : path.join(devRoot, 'resources');
  const startupDetails = [
    `timestamp=${new Date().toISOString()}`,
    `app.isPackaged=${app.isPackaged}`,
    `__dirname=${__dirname}`,
    `process.resourcesPath=${process.resourcesPath}`,
    `devRoot=${devRoot}`,
    `resolved backend path=${packagedBackend}`,
    `backend exists=${fs.existsSync(packagedBackend)}`,
    `resolved frontend index path=${frontendIndex}`,
    `frontend exists=${fs.existsSync(frontendIndex)}`,
    `resolved resource/model root=${resourceRoot}`,
    `resource root exists=${fs.existsSync(resourceRoot)}`,
    '',
  ];
  fs.appendFileSync(path.join(logs, 'electron-startup.log'), startupDetails.join('\n'));

  if (app.isPackaged) {
    if (!fs.existsSync(packagedBackend)) {
      throw new Error(`Packaged backend missing:\n${packagedBackend}`);
    }
    if (!fs.existsSync(frontendIndex)) {
      throw new Error(`Frontend build missing:\n${frontendIndex}`);
    }
    if (!fs.existsSync(resourceRoot)) {
      throw new Error(`Packaged resource root missing:\n${resourceRoot}`);
    }
  } else {
    if (!fs.existsSync(packagedBackend) && !fs.existsSync(python)) {
      throw new Error(`Development Python missing:\n${python}`);
    }
    if (!fs.existsSync(frontendIndex)) {
      throw new Error(`Frontend build missing:\n${frontendIndex}`);
    }
    if (!fs.existsSync(resourceRoot)) {
      throw new Error(`Development resource root missing:\n${resourceRoot}`);
    }
  }

  const usePackagedBackend = app.isPackaged || fs.existsSync(packagedBackend);
  const port = await availablePort();
  const origin = `http://127.0.0.1:${port}`;
  const log = fs.openSync(path.join(logs, 'backend.log'), 'a');
  const backendCommand = usePackagedBackend ? packagedBackend : python;
  const backendCwd = usePackagedBackend ? backendRoot : devRoot;
  const backendArgs = usePackagedBackend
    ? ['--host', '127.0.0.1', '--port', String(port)]
    : ['-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', String(port)];
  backend = spawn(backendCommand, backendArgs, {
    cwd: backendCwd, windowsHide: true, stdio: ['ignore', log, log],
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', RETINA_INSTANCE: instance,
      RETINA_RUNTIME_ROOT: runtimeRoot,
      RETINA_HISTORY_PATH: path.join(app.getPath('userData'), 'retinagram-history.json') }
  });
  fs.closeSync(log);
  let launchError;
  backend.once('error', error => { launchError = error; });
  backend.once('exit', () => {
    if (!stopping && BrowserWindow.getAllWindows().length) {
      dialog.showErrorBox('Inference backend stopped', 'Close and restart RetinaGram GPU. See the RetinaGram GPU local-data logs.');
      app.quit();
    }
  });
  let ready = false;
  for (let attempt = 0; attempt < 180; attempt++) {
    if (launchError) throw launchError;
    if (backend.exitCode !== null) throw new Error('Backend exited during startup. See the RetinaGram GPU local-data logs.');
    try {
      const response = await fetch(`${origin}/health`, { signal: AbortSignal.timeout(1000) });
      const status = await response.json();
      if (status.instance === instance) {
        if (!status.ready) throw new Error('No inference models loaded. Check work/logs/backend.log.');
        ready = true; break;
      }
    } catch (error) {
      if (error.message.startsWith('No inference')) throw error;
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  if (!ready) throw new Error('Backend startup timed out. See the RetinaGram GPU local-data logs.');
  const window = new BrowserWindow({ width: 1440, height: 960, minWidth: 800, minHeight: 650,
    title: 'RetinaGram GPU', icon: app.isPackaged
      ? path.join(backendRoot, '_internal', 'frontend', 'public', 'logo.png.jpeg')
      : path.join(devRoot, 'frontend', 'public', 'logo.png.jpeg'), backgroundColor: '#f8fafc',
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), nodeIntegration: false, contextIsolation: true, sandbox: true, backgroundThrottling: process.env.RETINA_SMOKE !== '1' }
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event, url) => { if (new URL(url).origin !== origin) event.preventDefault(); });
  await window.loadURL(process.env.RETINA_SMOKE === '1' ? `${origin}/?smoke=1` : origin);
  // Optional local integration smoke harness; never enabled in normal launches.
  if (process.env.RETINA_SMOKE === '1') {
    const smokeScript = process.env.RETINA_HISTORY_SMOKE === '1'
      ? './history-smoke.cjs'
      : process.env.RETINA_VISUAL_SMOKE === '1' ? './visual-smoke.cjs' : './smoke.cjs';
    const { runSmoke } = require(smokeScript);
    const smokeRoot = app.isPackaged ? app.getPath('userData') : devRoot;
    fs.mkdirSync(path.join(smokeRoot, 'work'), { recursive: true });
    try { await runSmoke(window, origin, smokeRoot, backend.pid); }
    catch (error) { fs.writeFileSync(path.join(smokeRoot, 'work', 'desktop-smoke-error.txt'), error.stack); process.exitCode = 1; }
    app.quit();
  }
}

ipcMain.handle('retinagram:choose-report-folder', async () => {
  if (process.env.RETINA_SMOKE === '1') {
    const smokeRoot = app.isPackaged ? app.getPath('userData') : devRoot;
    const destination = path.join(smokeRoot, 'work', 'test-report-exports');
    fs.mkdirSync(destination, { recursive: true });
    return destination;
  }
  const owner = BrowserWindow.getFocusedWindow();
  const result = await dialog.showOpenDialog(owner || undefined, {
    title: 'Choose RetinaGram report destination',
    buttonLabel: 'Select folder',
    properties: ['openDirectory', 'createDirectory'],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('retinagram:choose-batch-input-folder', async () => {
  if (process.env.RETINA_SMOKE === '1' && process.env.RETINA_BATCH_INPUT) {
    return path.resolve(process.env.RETINA_BATCH_INPUT);
  }
  const owner = BrowserWindow.getFocusedWindow();
  const result = await dialog.showOpenDialog(owner || undefined, {
    title: 'Choose RetinaGram batch input folder',
    buttonLabel: 'Choose folder',
    properties: ['openDirectory'],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('retinagram:choose-batch-output-folder', async () => {
  if (process.env.RETINA_SMOKE === '1') {
    const smokeRoot = app.isPackaged ? app.getPath('userData') : devRoot;
    const destination = process.env.RETINA_BATCH_OUTPUT || path.join(smokeRoot, 'work', 'test-batch-exports');
    fs.mkdirSync(destination, { recursive: true });
    return path.resolve(destination);
  }
  const owner = BrowserWindow.getFocusedWindow();
  const result = await dialog.showOpenDialog(owner || undefined, {
    title: 'Choose RetinaGram batch output folder',
    buttonLabel: 'Select folder',
    properties: ['openDirectory', 'createDirectory'],
  });
  return result.canceled ? null : result.filePaths[0];
});

if (!app.requestSingleInstanceLock()) app.quit();
else app.whenReady().then(start).catch(error => { dialog.showErrorBox('RetinaGram startup failed', error.message); app.quit(); });
app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => { stopping = true; if (backend && backend.exitCode === null) backend.kill(); });
