const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electron", {
    minimize: () => ipcRenderer.send("window-minimize"),
    maximize: () => ipcRenderer.send("window-maximize"),
    close: () => ipcRenderer.send("window-close"),
    selectDirectory: () => ipcRenderer.invoke("dialog-select-directory"),
    watchDirectory: (dirPath) => ipcRenderer.send("watch-directory", dirPath),
    onDirectoryChanged: (callback) => {
        const listener = (event, data) => callback(data);
        ipcRenderer.on("directory-changed", listener);
        return () => ipcRenderer.removeListener("directory-changed", listener);
    }
});
