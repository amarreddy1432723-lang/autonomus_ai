const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electron", {
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
        const listener = (event, data) => callback(data);
        ipcRenderer.on("update-available", listener);
        return () => ipcRenderer.removeListener("update-available", listener);
    },
    onUpdateReady: (callback) => {
        const listener = (event, data) => callback(data);
        ipcRenderer.on("update-ready", listener);
        return () => ipcRenderer.removeListener("update-ready", listener);
    },
    onUpdateStatus: (callback) => {
        const listener = (event, data) => callback(data);
        ipcRenderer.on("desktop-update-status", listener);
        return () => ipcRenderer.removeListener("desktop-update-status", listener);
    },
    onTerminalData: (callback) => {
        const listener = (event, data) => callback(data);
        ipcRenderer.on("terminal-data", listener);
        return () => ipcRenderer.removeListener("terminal-data", listener);
    },
    onTerminalExit: (callback) => {
        const listener = (event, data) => callback(data);
        ipcRenderer.on("terminal-exit", listener);
        return () => ipcRenderer.removeListener("terminal-exit", listener);
    },
    onDirectoryChanged: (callback) => {
        const listener = (event, data) => callback(data);
        ipcRenderer.on("directory-changed", listener);
        return () => ipcRenderer.removeListener("directory-changed", listener);
    },
    onFolderWatchError: (callback) => {
        const listener = (event, data) => callback(data);
        ipcRenderer.on("folder-watch-error", listener);
        return () => ipcRenderer.removeListener("folder-watch-error", listener);
    },
    onAuthCode: (callback) => {
        const listener = (event, data) => callback(data);
        ipcRenderer.on("desktop-auth-code", listener);
        return () => ipcRenderer.removeListener("desktop-auth-code", listener);
    }
});
