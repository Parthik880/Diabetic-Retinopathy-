const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('retinaDesktop', {
  contactPatient: action => ipcRenderer.invoke('retinagram:contact-patient', action),
  openDataFolder: () => ipcRenderer.invoke('retinagram:open-data-folder'),
  chooseReportFolder: () => ipcRenderer.invoke('retinagram:choose-report-folder'),
  chooseBatchInputFolder: () => ipcRenderer.invoke('retinagram:choose-batch-input-folder'),
  chooseBatchOutputFolder: () => ipcRenderer.invoke('retinagram:choose-batch-output-folder'),
});
