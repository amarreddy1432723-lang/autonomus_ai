const { app, BrowserWindow, Tray, Menu, ipcMain, dialog, globalShortcut } = require("electron");
const path = require("path");
const { spawn, exec } = require("child_process");
const isDev = require("electron-is-dev");

let mainWindow;
let launcherWindow;
let backendProcesses = [];
let frontendProcess = null;
const FRONTEND_ORIGIN = process.env.NEXUS_FRONTEND_URL || "http://localhost:3000";
const DEFAULT_ROUTE = process.env.NEXUS_DESKTOP_ROUTE || "/workspace";

const gotLock = app.requestSingleInstanceLock();

if (!gotLock) {
    app.quit();
} else {
    app.on("second-instance", () => {
        if (!mainWindow) return;
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.show();
        mainWindow.focus();
    });
}

async function waitForFrontend(attempts = 90) {
    for (let i = 0; i < attempts; i += 1) {
        try {
            const response = await fetch(FRONTEND_ORIGIN, { method: "HEAD" });
            if (response.ok || response.status < 500) return;
        } catch {
            // The dev server is still booting.
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
    }
}

async function loadFrontendRoute(windowRef, route) {
    await waitForFrontend();
    if (!windowRef || windowRef.isDestroyed()) return;
    const safeRoute = typeof route === "string" && route.startsWith("/") ? route : DEFAULT_ROUTE;
    windowRef.loadURL(`${FRONTEND_ORIGIN}${safeRoute}`);
}

function startBackendService(serviceName, entryPoint, port) {
    const rootDir = path.resolve(__dirname, "..");
    const backendDir = path.join(rootDir, "backend");
    
    let command = "uvicorn";
    let args = [entryPoint, "--host", "127.0.0.1", "--port", port.toString()];
    
    const isWindows = process.platform === "win32";
    const venvBin = isWindows 
        ? path.join(backendDir, ".venv", "Scripts") 
        : path.join(backendDir, ".venv", "bin");
        
    const uvicornPath = path.join(venvBin, isWindows ? "uvicorn.exe" : "uvicorn");
    
    const p = spawn(uvicornPath, args, {
        cwd: backendDir,
        env: {
            ...process.env,
            PORT: port.toString(),
            LOCAL_WORKSPACE_IMPORT_ENABLED: process.env.LOCAL_WORKSPACE_IMPORT_ENABLED || "true",
            LOCAL_WORKSPACE_ALLOWED_ROOTS: process.env.LOCAL_WORKSPACE_ALLOWED_ROOTS || (process.env.USERPROFILE || app.getPath("home")),
            ALLOW_DEV_AUTH_FALLBACK: process.env.ALLOW_DEV_AUTH_FALLBACK || "true"
        },
        shell: true
    });

    p.stdout.on("data", (data) => {
        console.log(`[${serviceName}] stdout: ${data}`);
    });

    p.stderr.on("data", (data) => {
        console.error(`[${serviceName}] stderr: ${data}`);
    });

    backendProcesses.push(p);
    console.log(`Started backend service: ${serviceName} on port ${port}`);
}

function startFrontendService() {
    const rootDir = path.resolve(__dirname, "..");
    const frontendDir = path.join(rootDir, "frontend");
    
    const command = "npm";
    const args = ["run", "dev"];
    
    frontendProcess = spawn(command, args, {
        cwd: frontendDir,
        env: {
            ...process.env,
            NEXT_PUBLIC_AUTH_URL: process.env.NEXT_PUBLIC_AUTH_URL || "http://localhost:8001",
            NEXT_PUBLIC_GOALS_URL: process.env.NEXT_PUBLIC_GOALS_URL || "http://localhost:8002",
            NEXT_PUBLIC_AGENT_URL: process.env.NEXT_PUBLIC_AGENT_URL || "http://localhost:8003",
            NEXT_PUBLIC_REQUIRE_AUTH: process.env.NEXT_PUBLIC_REQUIRE_AUTH || "false",
            BROWSER: "none"
        },
        shell: true
    });

    frontendProcess.stdout.on("data", (data) => {
        console.log(`[Frontend] stdout: ${data}`);
    });

    frontendProcess.stderr.on("data", (data) => {
        console.error(`[Frontend] stderr: ${data}`);
    });

    console.log("Started Next.js frontend developer server.");
}

function createLauncherWindow() {
    launcherWindow = new BrowserWindow({
        width: 600,
        height: 160,
        title: "NEXUS Launcher",
        frame: false,
        resizable: false,
        show: false,
        alwaysOnTop: true,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, "preload.js")
        },
        backgroundColor: "#0d0e12"
    });

    launcherWindow.setMenuBarVisibility(false);

    loadFrontendRoute(launcherWindow, "/launcher");

    launcherWindow.on("blur", () => {
        if (launcherWindow) launcherWindow.hide();
    });

    launcherWindow.on("closed", () => {
        launcherWindow = null;
    });
}

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1366,
        height: 768,
        title: "NEXUS OS",
        frame: false, // Frameless design for custom titles
        transparent: false,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, "preload.js")
        },
        backgroundColor: "#0d0e12"
    });

    mainWindow.setMenuBarVisibility(false);

    loadFrontendRoute(mainWindow, DEFAULT_ROUTE);

    mainWindow.on("closed", () => {
        mainWindow = null;
    });
}

// Window control IPC handlers
ipcMain.on("window-minimize", () => {
    if (mainWindow) mainWindow.minimize();
});

ipcMain.on("window-maximize", () => {
    if (mainWindow) {
        if (mainWindow.isMaximized()) {
            mainWindow.unmaximize();
        } else {
            mainWindow.maximize();
        }
    }
});

ipcMain.on("window-close", () => {
    if (mainWindow) mainWindow.close();
});

ipcMain.on("launcher-hide", () => {
    if (launcherWindow) launcherWindow.hide();
});

ipcMain.on("open-route", (_event, route) => {
    if (!mainWindow) createWindow();
    if (mainWindow) {
        mainWindow.show();
        mainWindow.focus();
        loadFrontendRoute(mainWindow, route);
    }
    if (launcherWindow) launcherWindow.hide();
});

// Select local directory IPC handler
ipcMain.handle("dialog-select-directory", async () => {
    if (!mainWindow) return null;
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ["openDirectory"]
    });
    if (result.canceled) {
        return null;
    }
    return result.filePaths[0];
});

let dirWatcher;

ipcMain.on("watch-directory", (event, dirPath) => {
    if (dirWatcher) {
        try {
            dirWatcher.close();
        } catch (e) {
            console.error("Failed to close existing watcher:", e);
        }
    }
    
    const chokidar = require("chokidar");
    dirWatcher = chokidar.watch(dirPath, {
        ignored: /(^|[\/\\])\../, // ignore dotfiles
        persistent: true,
        ignoreInitial: true
    });
    
    const sendChange = (changeEvent, filepath) => {
        if (mainWindow) {
            const relPath = path.relative(dirPath, filepath).replace(/\\/g, "/");
            mainWindow.webContents.send("directory-changed", {
                event: changeEvent,
                path: relPath,
                absolutePath: filepath
            });
        }
    };
    
    dirWatcher
        .on("add", (filepath) => sendChange("add", filepath))
        .on("change", (filepath) => sendChange("change", filepath))
        .on("unlink", (filepath) => sendChange("unlink", filepath));
        
    console.log(`Started watching directory: ${dirPath}`);
});

app.whenReady().then(() => {
    // 1. Launch local backend microservices
    startBackendService("auth-service", "services.auth.main:app", 8001);
    startBackendService("goals-service", "services.goals.main:app", 8002);
    startBackendService("agent-service", "services.agent.main:app", 8003);

    // 2. Launch Next.js frontend
    startFrontendService();

    // 3. Create native app UI window
    createWindow();
    createLauncherWindow();

    // 4. Register system-wide global shortcut to toggle launcher visibility
    const shortcutRegistered = globalShortcut.register("CommandOrControl+Shift+Space", () => {
        if (launcherWindow) {
            if (launcherWindow.isVisible()) {
                launcherWindow.hide();
            } else {
                launcherWindow.show();
                launcherWindow.focus();
            }
        }
    });
    if (!shortcutRegistered) {
        console.warn("Global launcher shortcut CommandOrControl+Shift+Space could not be registered.");
    }

    app.on("activate", () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
            createLauncherWindow();
        }
    });
});

app.on("will-quit", () => {
    // Unregister shortcuts
    globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
    // Terminate all background processes on exit
    console.log("Shutting down local NEXUS services...");
    backendProcesses.forEach(p => {
        try {
            if (process.platform === "win32") {
                exec(`taskkill /pid ${p.pid} /t /f`);
            } else {
                p.kill();
            }
        } catch (e) {
            console.error("Failed to kill backend process:", e);
        }
    });
    
    if (frontendProcess) {
        try {
            if (process.platform === "win32") {
                exec(`taskkill /pid ${frontendProcess.pid} /t /f`);
            } else {
                frontendProcess.kill();
            }
        } catch (e) {
            console.error("Failed to kill frontend process:", e);
        }
    }
    
    if (process.platform !== "darwin") {
        app.quit();
    }
});
