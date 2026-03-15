const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const Store = require('electron-store');

const store = new Store();
let mainWindow;
let backendProcess;

const BACKEND_PORT = 8765;
const BACKEND_READY_TIMEOUT = 15000; // 15초

function startBackend() {
  const pythonExecutable = process.platform === 'win32' ? 'python' : 'python3';
  const backendPath = path.join(__dirname, 'backend', 'main.py');

  backendProcess = spawn(pythonExecutable, [backendPath], {
    cwd: path.join(__dirname, 'backend'),
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  backendProcess.stdout.on('data', (data) => {
    console.log('[Backend]', data.toString());
  });

  backendProcess.stderr.on('data', (data) => {
    console.error('[Backend Error]', data.toString());
  });

  backendProcess.on('exit', (code) => {
    console.log(`[Backend] 프로세스 종료 (코드: ${code})`);
  });
}

async function waitForBackend() {
  const start = Date.now();
  while (Date.now() - start < BACKEND_READY_TIMEOUT) {
    try {
      const response = await fetch(`http://localhost:${BACKEND_PORT}/health`);
      if (response.ok) return true;
    } catch {
      // 아직 준비 중
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#1A1A2E',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    titleBarStyle: 'default',
    title: '회의록 자동작성',
  });

  mainWindow.loadFile(path.join(__dirname, 'frontend', 'index.html'));

  if (process.env.NODE_ENV === 'development') {
    mainWindow.webContents.openDevTools();
  }
}

// IPC: 설정 저장/불러오기
ipcMain.handle('store:get', (_, key) => store.get(key));
ipcMain.handle('store:set', (_, key, value) => store.set(key, value));
ipcMain.handle('store:delete', (_, key) => store.delete(key));

// IPC: 백엔드 상태 확인
ipcMain.handle('backend:health', async () => {
  try {
    const response = await fetch(`http://localhost:${BACKEND_PORT}/health`);
    return response.ok;
  } catch {
    return false;
  }
});

app.whenReady().then(async () => {
  startBackend();
  await createWindow();

  const ready = await waitForBackend();
  if (!ready) {
    mainWindow.webContents.send('backend:error', '백엔드 서버 시작에 실패했습니다. 앱을 다시 시작해 주세요.');
  } else {
    mainWindow.webContents.send('backend:ready');
  }
});

app.on('window-all-closed', () => {
  if (backendProcess) {
    backendProcess.kill();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (backendProcess) {
    backendProcess.kill();
  }
});
