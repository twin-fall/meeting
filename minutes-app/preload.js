const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // 로컬 설정 저장소 (API 키 등)
  store: {
    get: (key) => ipcRenderer.invoke('store:get', key),
    set: (key, value) => ipcRenderer.invoke('store:set', key, value),
    delete: (key) => ipcRenderer.invoke('store:delete', key),
  },
  // 백엔드 이벤트 수신
  onBackendReady: (callback) => ipcRenderer.on('backend:ready', callback),
  onBackendError: (callback) => ipcRenderer.on('backend:error', (_, msg) => callback(msg)),
  // 백엔드 헬스 체크
  checkBackend: () => ipcRenderer.invoke('backend:health'),
});
