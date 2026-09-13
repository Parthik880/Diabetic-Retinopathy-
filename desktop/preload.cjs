const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('retinaDesktop', {
  chooseReportFolder: () => ipcRenderer.invoke('retinagram:choose-report-folder'),
  openCommunication: request => ipcRenderer.invoke('retinagram:communicate', request),
  openDataFolder: () => ipcRenderer.invoke('retinagram:open-data-folder'),
  copyText: value => ipcRenderer.invoke('retinagram:copy-text', value),
});
