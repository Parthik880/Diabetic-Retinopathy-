const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('retinaDesktop', {
  chooseReportFolder: () => ipcRenderer.invoke('retinagram:choose-report-folder'),
});
