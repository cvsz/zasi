const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let pythonProcess;

function startBackend() {
  pythonProcess = spawn('python3', [path.join(__dirname, '../backend/server.py')], {
    env: { ...process.env, ZASI_PORT: '8080' }
  });
  pythonProcess.stdout.on('data', (data) => console.log(`[Python]: ${data}`));
  pythonProcess.stderr.on('data', (data) => console.error(`[Python Err]: ${data}`));
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    title: 'ZASI J.A.R.V.I.S. Omniversal Cockpit',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true
    }
  });

  setTimeout(() => {
    mainWindow.loadURL('http://localhost:8080');
  }, 1000);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  startBackend();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (pythonProcess) pythonProcess.kill();
  if (process.platform !== 'darwin') app.quit();
});
