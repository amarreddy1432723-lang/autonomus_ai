const { app, BrowserWindow, Tray, Menu } = require("electron");
const path = require("path");
const { spawn, exec } = require("child_process");
const isDev = require("electron-is-dev");

let mainWindow;
let backendProcesses = [];
let frontendProcess = null;

function startBackendService(serviceName, entryPoint, port) {
    const rootDir = path.resolve(__dirname, "..");
    const backendDir = path.join(rootDir, "backend");
    
    // Resolve virtual env python/uvicorn based on OS
    let command = "uvicorn";
    let args = [entryPoint, "--host", "127.0.0.1", "--port", port.toString()];
    
    const isWindows = process.platform === "win32";
    const venvBin = isWindows 
        ? path.join(backendDir, ".venv", "Scripts") 
        : path.join(backendDir, ".venv", "bin");
        
    const uvicornPath = path.join(venvBin, isWindows ? "uvicorn.exe" : "uvicorn");
    
    const p = spawn(uvicornPath, args, {
        cwd: backendDir,
        env: { ...process.env, PORT: port.toString() },
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
    
    // Spawn frontend start/dev
    const command = "npm";
    const args = ["run", "dev"];
    
    frontendProcess = spawn(command, args, {
        cwd: frontendDir,
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

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1366,
        height: 768,
        title: "NEXUS OS",
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, "preload.js")
        },
        backgroundColor: "#0d0e12"
    });

    mainWindow.setMenuBarVisibility(false);

    // Wait a brief moment for local Next.js server to spin up
    setTimeout(() => {
        mainWindow.loadURL("http://localhost:3000/hub");
    }, 4500);

    mainWindow.on("closed", () => {
        mainWindow = null;
    });
}

app.whenReady().then(() => {
    // 1. Launch local backend microservices
    startBackendService("auth-service", "services.auth.main:app", 8001);
    startBackendService("goals-service", "services.goals.main:app", 8002);
    startBackendService("agent-service", "services.agent.main:app", 8003);

    // 2. Launch Next.js frontend
    startFrontendService();

    // 3. Create native app UI window
    createWindow();

    app.on("activate", () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
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
