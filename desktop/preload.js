const { contextBridge, ipcRenderer } = require("electron");

function request(payload = {}, metadata = {}) {
    return {
        requestId: metadata.requestId || (globalThis.crypto?.randomUUID ? globalThis.crypto.randomUUID() : `req_${Date.now()}_${Math.random().toString(16).slice(2)}`),
        initiatedBy: metadata.initiatedBy || "user",
        missionId: metadata.missionId,
        agentId: metadata.agentId,
        payload
    };
}

function on(channel, callback) {
    const listener = (_event, data) => callback(data);
    ipcRenderer.on(channel, listener);
    return () => ipcRenderer.removeListener(channel, listener);
}

const legacyElectronApi = {
    isDesktop: true,
    minimize: () => ipcRenderer.send("window-minimize"),
    maximize: () => ipcRenderer.send("window-maximize"),
    close: () => ipcRenderer.send("window-close"),
    hideLauncher: () => ipcRenderer.send("launcher-hide"),
    openRoute: (route) => ipcRenderer.send("open-route", route),
    openExternal: (url) => ipcRenderer.invoke("desktop-open-external", url),
    selectDirectory: () => ipcRenderer.invoke("dialog-select-directory"),
    readDirectoryTree: (rootPath) => ipcRenderer.invoke("workspace-read-directory-tree", rootPath),
    readFile: (rootPath, relativePath) => ipcRenderer.invoke("workspace-read-file", rootPath, relativePath),
    writeFile: (rootPath, relativePath, content) => ipcRenderer.invoke("workspace-write-file", rootPath, relativePath, content),
    createItem: (rootPath, relativePath, type, content) => ipcRenderer.invoke("workspace-create-item", rootPath, relativePath, type, content),
    renameItem: (rootPath, fromRelativePath, toRelativePath) => ipcRenderer.invoke("workspace-rename-item", rootPath, fromRelativePath, toRelativePath),
    deleteItem: (rootPath, relativePath) => ipcRenderer.invoke("workspace-delete-item", rootPath, relativePath),
    revealItem: (rootPath, relativePath) => ipcRenderer.invoke("workspace-reveal-item", rootPath, relativePath),
    watchDirectory: (dirPath) => ipcRenderer.send("watch-directory", dirPath),
    stopWatchingDirectory: () => ipcRenderer.invoke("watch-directory-stop"),
    terminalCreate: (rootPath, options) => ipcRenderer.invoke("terminal-create", rootPath, options),
    terminalInput: (terminalId, input, options) => ipcRenderer.invoke("terminal-input", terminalId, input, options),
    terminalResize: (terminalId, cols, rows) => ipcRenderer.invoke("terminal-resize", terminalId, cols, rows),
    terminalKill: (terminalId) => ipcRenderer.invoke("terminal-kill", terminalId),
    installUpdate: () => ipcRenderer.invoke("desktop-install-update"),
    onUpdateAvailable: (callback) => {
        return on("update-available", callback);
    },
    onUpdateReady: (callback) => {
        return on("update-ready", callback);
    },
    onUpdateStatus: (callback) => {
        return on("desktop-update-status", callback);
    },
    onTerminalData: (callback) => {
        return on("terminal-data", callback);
    },
    onTerminalExit: (callback) => {
        return on("terminal-exit", callback);
    },
    onDirectoryChanged: (callback) => {
        return on("directory-changed", callback);
    },
    onFolderWatchError: (callback) => {
        return on("folder-watch-error", callback);
    },
    onAuthCode: (callback) => {
        return on("desktop-auth-code", callback);
    }
};

const arceusDesktopApi = {
    isDesktop: true,
    capabilities: () => ipcRenderer.invoke("desktop.capabilities", request()),
    diagnostics: () => ipcRenderer.invoke("desktop.diagnostics", request()),
    workspace: {
        openDirectory: (options = {}) => ipcRenderer.invoke("workspace.open", request(options)),
        setTrust: (rootPath, trusted) => ipcRenderer.invoke("workspace.trust", request({ rootPath, trusted })),
        readDirectoryTree: (rootPath) => ipcRenderer.invoke("workspace-read-directory-tree", rootPath),
        discoverTasks: (rootPath) => ipcRenderer.invoke("workspace.discoverTasks", request({ rootPath })),
    },
    filesystem: {
        readFile: (rootPath, relativePath) => ipcRenderer.invoke("filesystem.readFile", request({ rootPath, relativePath })),
        writeFile: (rootPath, relativePath, content) => ipcRenderer.invoke("filesystem.writeFile", request({ rootPath, relativePath, content })),
    },
    terminal: {
        create: (rootPath, options = {}) => ipcRenderer.invoke("terminal.create", request({ rootPath, ...options }, { initiatedBy: options.createdBy, missionId: options.missionId, agentId: options.agentId })),
        sendInput: (terminalId, input, options = {}) => ipcRenderer.invoke("terminal.sendInput", request({ terminalId, input, ...options })),
        resize: (terminalId, cols, rows) => ipcRenderer.invoke("terminal-resize", terminalId, cols, rows),
        kill: (terminalId) => ipcRenderer.invoke("terminal.kill", request({ terminalId })),
        onData: (callback) => on("terminal-data", callback),
        onExit: (callback) => on("terminal-exit", callback),
    },
    updater: {
        install: () => ipcRenderer.invoke("desktop-install-update"),
        onAvailable: (callback) => on("update-available", callback),
        onReady: (callback) => on("update-ready", callback),
        onStatus: (callback) => on("desktop-update-status", callback),
    },
    system: {
        minimize: legacyElectronApi.minimize,
        maximize: legacyElectronApi.maximize,
        close: legacyElectronApi.close,
        openExternal: legacyElectronApi.openExternal,
        openRoute: legacyElectronApi.openRoute,
        onAuthCode: legacyElectronApi.onAuthCode,
    },
};

contextBridge.exposeInMainWorld("electron", legacyElectronApi);
contextBridge.exposeInMainWorld("arceusDesktop", arceusDesktopApi);
