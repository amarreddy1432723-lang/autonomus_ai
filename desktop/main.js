const { app, BrowserWindow, Tray, Menu, ipcMain, dialog, globalShortcut } = require("electron");
const path = require("path");
const fs = require("fs");
const net = require("net");
const { spawn, exec } = require("child_process");
const isDev = require("electron-is-dev");

let mainWindow;
let launcherWindow;
let backendProcesses = [];
let frontendProcess = null;
let frontendOrigin = process.env.NEXUS_FRONTEND_URL || "http://localhost:3000";
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
            const response = await fetch(frontendOrigin, { method: "HEAD" });
            if (response.ok || response.status < 500) return;
        } catch {
            // The dev server is still booting.
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
    }
}

async function urlResponds(url, attempts = 1) {
    for (let i = 0; i < attempts; i += 1) {
        try {
            const response = await fetch(url, { method: "HEAD" });
            if (response.ok || response.status < 500) return true;
        } catch {
            // Port is not ready yet.
        }
        if (i < attempts - 1) {
            await new Promise((resolve) => setTimeout(resolve, 300));
        }
    }
    return false;
}

async function serviceResponds(port) {
    return urlResponds(`http://127.0.0.1:${port}/docs`) || urlResponds(`http://127.0.0.1:${port}/`);
}

function isPortFree(port) {
    return new Promise((resolve) => {
        const server = net.createServer();
        server.once("error", () => resolve(false));
        server.once("listening", () => {
            server.close(() => resolve(true));
        });
        server.listen(port);
    });
}

async function resolveFrontendOrigin() {
    if (process.env.NEXUS_FRONTEND_URL) {
        frontendOrigin = process.env.NEXUS_FRONTEND_URL;
        return { origin: frontendOrigin, port: new URL(frontendOrigin).port || "3000", reuse: await urlResponds(frontendOrigin) };
    }

    for (let port = 3000; port <= 3010; port += 1) {
        const origin = `http://localhost:${port}`;
        if (await urlResponds(origin)) {
            frontendOrigin = origin;
            return { origin, port: String(port), reuse: true };
        }
        if (await isPortFree(port)) {
            frontendOrigin = origin;
            return { origin, port: String(port), reuse: false };
        }
    }

    throw new Error("No available frontend port found between 3000 and 3010.");
}

async function loadFrontendRoute(windowRef, route) {
    await waitForFrontend();
    if (!windowRef || windowRef.isDestroyed()) return;
    const safeRoute = typeof route === "string" && route.startsWith("/") ? route : DEFAULT_ROUTE;
    windowRef.loadURL(`${frontendOrigin}${safeRoute}`);
}

function findRepoRoot() {
    const starts = [
        process.env.NEXUS_REPO_ROOT,
        __dirname,
        process.cwd(),
        app.getAppPath()
    ].filter(Boolean);

    for (const start of starts) {
        let current = path.resolve(start);
        while (true) {
            const hasBackend = fs.existsSync(path.join(current, "backend", "services"));
            const hasFrontend = fs.existsSync(path.join(current, "frontend", "package.json"));
            if (hasBackend && hasFrontend) return current;

            const parent = path.dirname(current);
            if (parent === current) break;
            current = parent;
        }
    }

    throw new Error("Could not find NEXUS repo root. Set NEXUS_REPO_ROOT to the folder that contains backend and frontend.");
}

function getBackendEnv(port) {
    return {
        ...process.env,
        PORT: port.toString(),
        LOCAL_WORKSPACE_IMPORT_ENABLED: process.env.LOCAL_WORKSPACE_IMPORT_ENABLED || "true",
        LOCAL_WORKSPACE_ALLOWED_ROOTS: process.env.LOCAL_WORKSPACE_ALLOWED_ROOTS || (process.env.USERPROFILE || app.getPath("home")),
        ALLOW_DEV_AUTH_FALLBACK: process.env.ALLOW_DEV_AUTH_FALLBACK || "true"
    };
}

async function startBackendService(serviceName, entryPoint, port) {
    if (await serviceResponds(port)) {
        console.log(`Reusing existing backend service: ${serviceName} on port ${port}`);
        return;
    }

    const rootDir = findRepoRoot();
    const backendDir = path.join(rootDir, "backend");
    
    const isWindows = process.platform === "win32";
    const venvBin = isWindows 
        ? path.join(backendDir, ".venv", "Scripts") 
        : path.join(backendDir, ".venv", "bin");
        
    const uvicornPath = path.join(venvBin, isWindows ? "uvicorn.exe" : "uvicorn");
    const pythonPath = path.join(venvBin, isWindows ? "python.exe" : "python");
    const hasUvicorn = fs.existsSync(uvicornPath);
    const hasPython = fs.existsSync(pythonPath);
    const command = hasUvicorn ? uvicornPath : (hasPython ? pythonPath : "python");
    const args = hasUvicorn
        ? [entryPoint, "--host", "127.0.0.1", "--port", port.toString()]
        : ["-m", "uvicorn", entryPoint, "--host", "127.0.0.1", "--port", port.toString()];
    
    const p = spawn(command, args, {
        cwd: backendDir,
        env: getBackendEnv(port),
        shell: false
    });

    p.on("error", (error) => {
        console.error(`[${serviceName}] failed to start: ${error.message}`);
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

async function startFrontendService() {
    const resolved = await resolveFrontendOrigin();
    if (resolved.reuse) {
        console.log(`Reusing existing Next.js frontend at ${resolved.origin}`);
        return;
    }

    const rootDir = findRepoRoot();
    const frontendDir = path.join(rootDir, "frontend");
    
    const command = process.platform === "win32" ? "npm.cmd" : "npm";
    const args = ["run", "dev"];
    
    frontendProcess = spawn(command, args, {
        cwd: frontendDir,
        env: {
            ...process.env,
            NEXT_PUBLIC_AUTH_URL: process.env.NEXT_PUBLIC_AUTH_URL || "http://localhost:8001",
            NEXT_PUBLIC_GOALS_URL: process.env.NEXT_PUBLIC_GOALS_URL || "http://localhost:8002",
            NEXT_PUBLIC_AGENT_URL: process.env.NEXT_PUBLIC_AGENT_URL || "http://localhost:8003",
            NEXT_PUBLIC_REQUIRE_AUTH: process.env.NEXT_PUBLIC_REQUIRE_AUTH || "false",
            PORT: resolved.port,
            BROWSER: "none"
        },
        shell: false
    });

    frontendProcess.on("error", (error) => {
        console.error(`[Frontend] failed to start: ${error.message}`);
    });

    frontendProcess.stdout.on("data", (data) => {
        console.log(`[Frontend] stdout: ${data}`);
    });

    frontendProcess.stderr.on("data", (data) => {
        console.error(`[Frontend] stderr: ${data}`);
    });

    console.log(`Started Next.js frontend developer server at ${resolved.origin}.`);
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

app.whenReady().then(async () => {
    // 1. Launch local backend microservices
    await startBackendService("auth-service", "services.auth.main:app", 8001);
    await startBackendService("goals-service", "services.goals.main:app", 8002);
    await startBackendService("agent-service", "services.agent.main:app", 8003);

    // 2. Launch Next.js frontend
    await startFrontendService();

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
