const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('retinaDesktop', {
  chooseReportFolder: () => ipcRenderer.invoke('retinagram:choose-report-folder'),
  chooseBatchInputFolder: () => ipcRenderer.invoke('retinagram:choose-batch-input-folder'),
  chooseBatchOutputFolder: () => ipcRenderer.invoke('retinagram:choose-batch-output-folder'),
});
