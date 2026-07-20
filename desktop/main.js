const { app, BrowserWindow, Tray, Menu, ipcMain, dialog, globalShortcut, shell } = require("electron");
const path = require("path");
const fs = require("fs");
const net = require("net");
const { spawn, exec } = require("child_process");
const isDev = require("electron-is-dev");
const {
    DESKTOP_CAPABILITIES,
    desktopError,
    ipcFail,
    ipcOk,
    isAllowedExternalUrl,
    safeJoinUrl,
    unwrapIpcPayload,
    workspaceIdFor
} = require("./architecture");
const { discoverWorkspaceTasks } = require("./task-discovery");

function installSafeConsole() {
    const wrap = (method) => {
        const original = console[method]?.bind(console);
        if (!original) return;
        console[method] = (...args) => {
            try {
                original(...args);
            } catch (error) {
                if (error?.code !== "EPIPE") {
                    try {
                        process.stderr.write(`[console-${method}-failed] ${error?.message || error}\n`);
                    } catch {
                        // Ignore secondary logging failures. Logging should never crash the desktop app.
                    }
                }
            }
        };
    };

    ["log", "warn", "error", "info"].forEach(wrap);
    process.stdout?.on?.("error", (error) => {
        if (error?.code !== "EPIPE") throw error;
    });
    process.stderr?.on?.("error", (error) => {
        if (error?.code !== "EPIPE") throw error;
    });
}

installSafeConsole();

let autoUpdater = null;
try {
    autoUpdater = require("electron-updater").autoUpdater;
} catch {
    autoUpdater = null;
}
let nodePty = null;
try {
    nodePty = require("node-pty");
} catch {
    nodePty = null;
}

let mainWindow;
let launcherWindow;
let backendProcesses = [];
let frontendProcess = null;
const PACKAGED_FRONTEND_URL = process.env.ARCEUS_WEB_URL || "https://frontend-production-fbde.up.railway.app";
let frontendOrigin = process.env.NEXUS_FRONTEND_URL || (isDev ? "http://localhost:3000" : PACKAGED_FRONTEND_URL);
let terminalSessions = new Map();
let trustedWorkspaces = new Map();
let dirWatcher;
let dirWatcherRoot = "";
let dirWatcherBatch = [];
let dirWatcherTimer = null;
let managedPostgres = null;
const DEFAULT_ROUTE = process.env.NEXUS_DESKTOP_ROUTE || "/launch";
const DESKTOP_CODE_ALLOWED_ROUTE_PREFIXES = [
    "/launch",
    "/workspace",
    "/idea-discovery",
    "/product-intelligence",
    "/domain-intelligence",
    "/product-blueprint",
    "/architecture-strategy",
    "/technology-stack",
    "/engineering-roadmap",
    "/ai-workforce",
    "/executive-review",
    "/mission-control",
    "/evolution-center",
    "/knowledge-graph",
    "/organization-network",
    "/intelligence-kernel",
    "/settings",
    "/auth/desktop",
    "/download",
    "/ui-preview"
];
const WORKSPACE_IGNORED_DIRS = new Set([".git", ".hg", ".svn", "node_modules", ".next", "dist", "build", "coverage", ".venv", "venv", "__pycache__", "pycache", ".pytest_cache", ".turbo", ".cache"]);
const WORKSPACE_IGNORED_EXTS = new Set([".pyc", ".pyo", ".map"]);
const WORKSPACE_MAX_TREE_FILES = Number(process.env.NEXUS_DESKTOP_MAX_TREE_FILES || 5000);
const WORKSPACE_MAX_FILE_BYTES = Number(process.env.NEXUS_DESKTOP_MAX_FILE_BYTES || 1500000);

function sanitizeDesktopCodeRoute(route) {
    let candidate = typeof route === "string" && route.trim() ? route.trim() : DEFAULT_ROUTE;
    try {
        if (/^https?:\/\//i.test(candidate)) {
            const parsed = new URL(candidate);
            candidate = `${parsed.pathname || "/"}${parsed.search || ""}${parsed.hash || ""}`;
        }
    } catch {
        candidate = DEFAULT_ROUTE;
    }

    if (!candidate.startsWith("/")) {
        candidate = DEFAULT_ROUTE;
    }

    const pathOnly = candidate.split("?")[0].split("#")[0];
    const allowed = DESKTOP_CODE_ALLOWED_ROUTE_PREFIXES.some((prefix) => (
        pathOnly === prefix || pathOnly.startsWith(`${prefix}/`)
    ));

    return allowed ? candidate : DEFAULT_ROUTE;
}

function configureAutoUpdater() {
    if (!autoUpdater || isDev || process.env.ARCEUS_DISABLE_AUTO_UPDATE === "true") {
        return;
    }
    autoUpdater.autoDownload = true;
    autoUpdater.autoInstallOnAppQuit = true;
    autoUpdater.on("checking-for-update", () => console.log("Checking for Arceus updates..."));
    autoUpdater.on("update-available", (info) => {
        console.log(`Arceus update available: ${info.version || "unknown"}`);
        if (mainWindow) {
            mainWindow.webContents.send("update-available", {
                version: info.version || "",
            });
            mainWindow.webContents.send("desktop-update-status", {
                status: "available",
                version: info.version || "",
            });
        }
    });
    autoUpdater.on("update-not-available", () => console.log("Arceus is up to date."));
    autoUpdater.on("download-progress", (progress) => {
        if (mainWindow) {
            mainWindow.webContents.send("desktop-update-status", {
                status: "downloading",
                percent: Math.round(progress.percent || 0),
            });
        }
    });
    autoUpdater.on("update-downloaded", (info) => {
        console.log(`Arceus update downloaded: ${info.version || "unknown"}`);
        if (!mainWindow) return;
        mainWindow.webContents.send("update-ready", {
            version: info.version || "",
        });
        mainWindow.webContents.send("desktop-update-status", {
            status: "ready",
            version: info.version || "",
        });
        dialog.showMessageBox(mainWindow, {
            type: "info",
            buttons: ["Restart now", "Later"],
            defaultId: 0,
            cancelId: 1,
            title: "Arceus update ready",
            message: "A new Arceus version has been downloaded.",
            detail: "Restart the app to install the update.",
        }).then((result) => {
            if (result.response === 0) {
                autoUpdater.quitAndInstall(false, true);
            }
        }).catch(() => {});
    });
    autoUpdater.on("error", (error) => {
        console.warn("Auto-update failed:", error?.message || error);
        if (mainWindow) {
            mainWindow.webContents.send("desktop-update-status", {
                status: "error",
                message: error?.message || String(error),
            });
        }
    });
}

ipcMain.handle("desktop-install-update", async () => {
    if (!autoUpdater || isDev || process.env.ARCEUS_DISABLE_AUTO_UPDATE === "true") {
        return { ok: false, message: "Auto-update is unavailable in this build." };
    }
    autoUpdater.quitAndInstall(false, true);
    return { ok: true };
});

ipcMain.handle("desktop-open-external", async (event, targetUrl) => {
    try {
        const frontend = new URL(frontendOrigin);
        const packaged = new URL(PACKAGED_FRONTEND_URL);
        const allowedHosts = new Set([frontend.host, packaged.host, "localhost:3000", "127.0.0.1:3000"]);
        if (!isAllowedExternalUrl(targetUrl, allowedHosts)) {
            return { ok: false, message: "External URL is not allowed." };
        }
        const parsed = new URL(String(targetUrl || ""));
        await shell.openExternal(parsed.toString());
        return { ok: true };
    } catch (error) {
        return { ok: false, message: error?.message || "Could not open external URL." };
    }
});

ipcMain.handle("desktop.capabilities", async (_event, request = {}) => {
    const { requestId } = unwrapIpcPayload([request]);
    return ipcOk(requestId, {
        ...DESKTOP_CAPABILITIES,
        autoUpdate: Boolean(autoUpdater) && !isDev && process.env.ARCEUS_DISABLE_AUTO_UPDATE !== "true",
        terminalBackend: nodePty ? "node-pty" : "child-process",
        hostedControlPlane: shouldUseHostedControlPlane(),
        frontendOrigin
    });
});

ipcMain.handle("desktop.diagnostics", async (_event, request = {}) => {
    const { requestId } = unwrapIpcPayload([request]);
    const userData = app.getPath("userData");
    const repoRoot = tryFindRepoRoot();
    return ipcOk(requestId, {
        appVersion: app.getVersion(),
        isDev,
        platform: process.platform,
        arch: process.arch,
        frontendOrigin,
        repoRoot,
        userData,
        backendProcesses: backendProcesses.map((processRef) => ({ pid: processRef.pid, killed: processRef.killed })),
        frontendProcess: frontendProcess ? { pid: frontendProcess.pid, killed: frontendProcess.killed } : null,
        terminalSessions: Array.from(terminalSessions.values()).map((session) => ({
            id: session.id,
            cwd: session.cwd,
            shell: session.shell,
            status: session.status,
            backend: session.backend,
            createdBy: session.createdBy,
            missionId: session.missionId,
            agentId: session.agentId,
            updatedAt: session.updated_at
        })),
        trustedWorkspaces: Array.from(trustedWorkspaces.values()),
        logFile: path.join(userData, "arceus-desktop.log")
    });
});

function checkForAppUpdates() {
    if (!autoUpdater || isDev || process.env.ARCEUS_DISABLE_AUTO_UPDATE === "true") {
        return;
    }
    autoUpdater.checkForUpdatesAndNotify().catch((error) => {
        console.warn("Update check failed:", error?.message || error);
    });
}

if (process.defaultApp) {
    if (process.argv.length >= 2) {
        app.setAsDefaultProtocolClient("arceus", process.execPath, [path.resolve(process.argv[1])]);
    }
} else {
    app.setAsDefaultProtocolClient("arceus");
}

function handleDeepLink(url) {
    console.log("Deep link received in desktop app:", url);
    try {
        const parsedUrl = new URL(url);
        if (parsedUrl.hostname === "auth" && parsedUrl.pathname === "/callback") {
            const code = parsedUrl.searchParams.get("code");
            if (code && mainWindow) {
                mainWindow.webContents.send("desktop-auth-code", { code });
            }
        }
    } catch (err) {
        console.error("Failed to parse deep link:", err.message);
    }
}

app.on("open-url", (event, url) => {
    event.preventDefault();
    if (url.startsWith("arceus://")) {
        handleDeepLink(url);
    }
});

const gotLock = app.requestSingleInstanceLock();

if (!gotLock) {
    app.quit();
} else {
    app.on("second-instance", (event, commandLine) => {
        if (!mainWindow) return;
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.show();
        mainWindow.focus();

        const url = commandLine.find((arg) => arg.startsWith("arceus://"));
        if (url) {
            handleDeepLink(url);
        }
    });
}

async function waitForFrontend(attempts = 90) {
    for (let i = 0; i < attempts; i += 1) {
        if (await frontendResponds(frontendOrigin)) return;
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

function tcpPortResponds(port, host = "127.0.0.1") {
    return new Promise((resolve) => {
        const socket = net.createConnection({ host, port, timeout: 1000 }, () => {
            socket.destroy();
            resolve(true);
        });
        socket.once("timeout", () => {
            socket.destroy();
            resolve(false);
        });
        socket.once("error", () => resolve(false));
    });
}

async function waitForTcpPort(port, attempts = 60) {
    for (let i = 0; i < attempts; i += 1) {
        if (await tcpPortResponds(port)) return true;
        await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    return false;
}

function configureLocalDatabase(port, options = {}) {
    const user = options.user || process.env.NEXUS_LOCAL_POSTGRES_USER || process.env.POSTGRES_USER || "postgres";
    const configuredPassword = options.password ?? process.env.NEXUS_LOCAL_POSTGRES_PASSWORD ?? process.env.POSTGRES_PASSWORD;
    const password = configuredPassword ? configuredPassword : "postgrespassword";
    const auth = password ? `${encodeURIComponent(user)}:${encodeURIComponent(password)}` : encodeURIComponent(user);
    const url = `postgresql+psycopg://${auth}@127.0.0.1:${port}/my_ai_db`;
    process.env.DATABASE_URL = url;
    process.env.AUTH_DATABASE_URL = url;
    process.env.GOALS_DATABASE_URL = url;
    process.env.AGENT_DATABASE_URL = url;
    process.env.DB_CONNECT_TIMEOUT_SECONDS = process.env.DB_CONNECT_TIMEOUT_SECONDS || "3";
    return url;
}

function findLocalPostgresInstallation() {
    const configuredBin = process.env.NEXUS_PG_BIN;
    const configuredData = process.env.NEXUS_PG_DATA;
    const candidates = [];

    if (configuredBin) {
        candidates.push({ binDir: configuredBin, dataDir: configuredData || path.join(path.dirname(configuredBin), "data") });
    }

    if (process.platform === "win32") {
        const postgresRoot = path.join(process.env.ProgramFiles || "C:\\Program Files", "PostgreSQL");
        if (fs.existsSync(postgresRoot)) {
            const versions = fs.readdirSync(postgresRoot, { withFileTypes: true })
                .filter((entry) => entry.isDirectory())
                .map((entry) => entry.name)
                .sort((left, right) => Number(right) - Number(left));
            for (const version of versions) {
                const installDir = path.join(postgresRoot, version);
                candidates.push({ binDir: path.join(installDir, "bin"), dataDir: configuredData || path.join(installDir, "data") });
            }
        }
    }

    for (const candidate of candidates) {
        const executable = (name) => path.join(candidate.binDir, process.platform === "win32" ? `${name}.exe` : name);
        const pgCtl = executable("pg_ctl");
        const psql = executable("psql");
        if (fs.existsSync(pgCtl) && fs.existsSync(psql) && fs.existsSync(path.join(candidate.dataDir, "PG_VERSION"))) {
            return { ...candidate, pgCtl, psql };
        }
    }
    return null;
}

async function ensureLocalPostgresDatabase(psql, port) {
    const env = { ...process.env, PGCONNECT_TIMEOUT: "3" };
    const check = await runProcess(psql, [
        "-h", "127.0.0.1", "-p", String(port), "-U", "postgres", "-d", "postgres",
        "-tAc", "SELECT 1 FROM pg_database WHERE datname='my_ai_db'"
    ], { env });
    if (check.stdout.trim() !== "1") {
        await runProcess(psql, [
            "-h", "127.0.0.1", "-p", String(port), "-U", "postgres", "-d", "postgres",
            "-v", "ON_ERROR_STOP=1", "-c", "CREATE DATABASE my_ai_db"
        ], { env });
    }
}

async function startInstalledPostgresFallback() {
    const installation = findLocalPostgresInstallation();
    if (!installation) return false;

    const port = Number(process.env.NEXUS_LOCAL_POSTGRES_PORT || 55432);
    if (await tcpPortResponds(port)) {
        configureLocalDatabase(port);
        console.log(`Reusing Arceus local PostgreSQL on port ${port}.`);
        return true;
    }

    const runtimeDir = path.join(app.getPath("userData"), "postgres-runtime");
    fs.mkdirSync(runtimeDir, { recursive: true });
    const hbaFile = path.join(runtimeDir, "pg_hba.conf");
    const logFile = path.join(runtimeDir, "postgres.log");
    fs.writeFileSync(
        hbaFile,
        [
            "local all all trust",
            "host all all 127.0.0.1/32 trust",
            "host all all ::1/128 trust",
            ""
        ].join("\n"),
        "utf8"
    );

    const hbaOption = hbaFile.replace(/\\/g, "/").replace(/'/g, "''");
    try {
        console.log(`Starting installed PostgreSQL for Arceus on port ${port}...`);
        await runProcess(installation.pgCtl, [
            "start", "-D", installation.dataDir,
            "-o", `-h 127.0.0.1 -p ${port} -c hba_file='${hbaOption}'`,
            "-l", logFile, "-w"
        ], { env: process.env });
        if (!(await waitForTcpPort(port, 20))) return false;
        await ensureLocalPostgresDatabase(installation.psql, port);
        configureLocalDatabase(port);
        managedPostgres = { ...installation, port };
        console.log(`Arceus local PostgreSQL is ready on port ${port}.`);
        return true;
    } catch (error) {
        console.error(`Installed PostgreSQL fallback failed: ${error.message}`);
        console.error(`PostgreSQL log: ${logFile}`);
        return false;
    }
}

function runProcess(command, args, options = {}) {
    return new Promise((resolve, reject) => {
        const child = spawn(command, args, {
            ...options,
            shell: false,
        });
        let stdout = "";
        let stderr = "";
        child.stdout?.on("data", (data) => {
            stdout += data.toString();
        });
        child.stderr?.on("data", (data) => {
            stderr += data.toString();
        });
        child.once("error", reject);
        child.once("close", (code) => {
            if (code === 0) {
                resolve({ stdout, stderr });
            } else {
                reject(new Error(stderr || stdout || `${command} exited with ${code}`));
            }
        });
    });
}

async function startLocalDependencies() {
    if (shouldUseHostedControlPlane()) {
        console.log(`Packaged Arceus install detected without local repo. Using hosted control plane: ${PACKAGED_FRONTEND_URL}`);
        return false;
    }
    if (process.env.NEXUS_SKIP_DOCKER_DEPS === "true") return true;

    const configuredDatabase = process.env.AGENT_DATABASE_URL || process.env.DATABASE_URL;
    if (configuredDatabase && !/(localhost|127\.0\.0\.1)/i.test(configuredDatabase)) {
        console.log("Using configured external database; skipping local Postgres startup.");
        return true;
    }

    const nexusLocalPort = Number(process.env.NEXUS_LOCAL_POSTGRES_PORT || 55432);
    if (await tcpPortResponds(nexusLocalPort)) {
        configureLocalDatabase(nexusLocalPort);
        managedPostgres = findLocalPostgresInstallation();
        console.log(`Reusing Arceus local PostgreSQL on port ${nexusLocalPort}.`);
        return true;
    }

    const postgresReady = await tcpPortResponds(5432);
    const redisReady = await tcpPortResponds(6379);
    if (postgresReady && redisReady) {
        configureLocalDatabase(5432);
        console.log("Reusing local Docker Postgres and Redis.");
        return true;
    }

    const rootDir = findRepoRoot();
    const composeFile = path.join(rootDir, "docker-compose.yml");
    if (!fs.existsSync(composeFile)) {
        console.warn("docker-compose.yml not found; skipping local dependency startup.");
        if (postgresReady) {
            configureLocalDatabase(5432);
        }
        return postgresReady || await startInstalledPostgresFallback();
    }

    const dockerCommand = process.platform === "win32" ? "docker.exe" : "docker";
    try {
        console.log("Starting local Postgres and Redis with Docker Compose...");
        await runProcess(dockerCommand, ["compose", "up", "-d", "postgres", "redis"], { cwd: rootDir, env: process.env });
    } catch (error) {
        console.error(`Could not start Docker dependencies: ${error.message}`);
        console.warn("Docker Desktop is unavailable. Trying installed PostgreSQL fallback...");
        if (postgresReady) {
            configureLocalDatabase(5432);
        }
        const fallbackReady = postgresReady || await startInstalledPostgresFallback();
        if (!fallbackReady) {
            console.error("Start Docker Desktop, then run: docker compose up -d postgres redis");
        }
        return fallbackReady;
    }

    const postgresStarted = await waitForTcpPort(5432, 90);
    const redisStarted = await waitForTcpPort(6379, 30);
    if (!postgresStarted) {
        console.error("Postgres did not become ready on port 5432. Agent service may fail until the database is running.");
    }
    if (!redisStarted) {
        console.warn("Redis did not become ready on port 6379. Rate limiting and short-term memory will fail open.");
    }
    if (postgresStarted) {
        configureLocalDatabase(5432);
    }
    return postgresStarted;
}

function resolveWorkspacePath(rootPath, relativePath = "") {
    if (!rootPath) throw new Error("Workspace root is required.");
    const root = path.resolve(rootPath);
    const requestedRelative = String(relativePath || ".");
    if (requestedRelative.includes("\0")) {
        throw new Error("Invalid workspace path.");
    }
    const target = path.resolve(root, relativePath || ".");
    const relative = path.relative(root, target);
    if (relative.startsWith("..") || path.isAbsolute(relative)) {
        throw new Error("Path is outside the trusted workspace.");
    }
    return { root, target, relative: relative.replace(/\\/g, "/") };
}

async function resolveWorkspacePathStrict(rootPath, relativePath = "") {
    const resolved = resolveWorkspacePath(rootPath, relativePath);
    const rootReal = await fs.promises.realpath(resolved.root).catch(() => resolved.root);
    const targetParent = await fs.promises.realpath(path.dirname(resolved.target)).catch(() => path.dirname(resolved.target));
    const candidate = path.resolve(targetParent, path.basename(resolved.target));
    const relative = path.relative(rootReal, candidate);
    if (relative.startsWith("..") || path.isAbsolute(relative)) {
        throw new Error("Path is outside the trusted workspace.");
    }
    return {
        root: rootReal,
        target: candidate,
        relative: path.relative(rootReal, candidate).replace(/\\/g, "/")
    };
}

async function atomicWriteFile(target, data) {
    const directory = path.dirname(target);
    await fs.promises.mkdir(directory, { recursive: true });
    const tempPath = path.join(directory, `.arceus-${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}.tmp`);
    const handle = await fs.promises.open(tempPath, "wx");
    try {
        await handle.writeFile(data);
        await handle.sync();
    } finally {
        await handle.close();
    }
    await fs.promises.rename(tempPath, target);
}

async function inspectWorkspace(rootPath) {
    const { root } = resolveWorkspacePath(rootPath);
    const stat = await fs.promises.stat(root);
    if (!stat.isDirectory()) throw new Error("Workspace root must be a directory.");
    const id = workspaceIdFor(root);
    const repoType = fs.existsSync(path.join(root, ".git")) ? "git" : "none";
    const now = new Date().toISOString();
    const previous = trustedWorkspaces.get(root);
    const workspace = {
        id,
        name: path.basename(root) || root,
        rootPath: root,
        repositoryType: repoType,
        trusted: Boolean(previous?.trusted),
        openedAt: previous?.openedAt || now,
        lastOpenedAt: now,
        settingsPath: path.join(root, ".arceus", "workspace.json")
    };
    trustedWorkspaces.set(root, workspace);
    return workspace;
}

function isIgnoredWorkspacePath(relativePath) {
    const normalized = String(relativePath || "").replace(/\\/g, "/");
    if (!normalized) return false;
    if (WORKSPACE_IGNORED_EXTS.has(path.extname(normalized).toLowerCase())) return true;
    return normalized
        .split(/[\\/]/)
        .some((part) => WORKSPACE_IGNORED_DIRS.has(part) || /^__pycache__$/.test(part));
}

async function readWorkspaceTree(rootPath) {
    const { root } = resolveWorkspacePath(rootPath);
    const items = [];
    async function walk(current, base = "") {
        if (items.length >= WORKSPACE_MAX_TREE_FILES) return;
        const entries = await fs.promises.readdir(current, { withFileTypes: true });
        for (const entry of entries) {
            const rel = base ? `${base}/${entry.name}` : entry.name;
            if (isIgnoredWorkspacePath(rel)) continue;
            const full = path.join(current, entry.name);
            if (entry.isDirectory()) {
                items.push({ path: rel, type: "folder" });
                await walk(full, rel);
            } else if (entry.isFile()) {
                const stat = await fs.promises.stat(full);
                if (stat.size <= WORKSPACE_MAX_FILE_BYTES) {
                    items.push({ path: rel, type: "file", size_bytes: stat.size });
                }
            }
            if (items.length >= WORKSPACE_MAX_TREE_FILES) break;
        }
    }
    await walk(root);
    return { root, items, count: items.length };
}

async function serviceResponds(port, attempts = 1) {
    return urlResponds(`http://127.0.0.1:${port}/docs`, attempts) || urlResponds(`http://127.0.0.1:${port}/`, attempts);
}

async function frontendResponds(origin, attempts = 1) {
    const normalized = origin.replace(/\/$/, "");
    for (let i = 0; i < attempts; i += 1) {
        try {
            const response = await fetch(`${normalized}/workspace`, { method: "HEAD" });
            if (response.ok) return true;
        } catch {
            // The frontend may still be booting or this port belongs to another app.
        }
        if (i < attempts - 1) {
            await new Promise((resolve) => setTimeout(resolve, 300));
        }
    }
    return false;
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

function frontendDevLockExists(frontendDir) {
    return fs.existsSync(path.join(frontendDir, ".next", "dev", "lock"));
}

async function detectExistingNextFrontend(frontendDir) {
    const defaultOrigin = "http://localhost:3000";
    if (await frontendResponds(defaultOrigin, 3)) {
        frontendOrigin = defaultOrigin;
        return { origin: defaultOrigin, port: "3000", reuse: true };
    }

    const defaultPortFree = await isPortFree(3000);
    const hasNextLock = frontendDevLockExists(frontendDir);
    if (!defaultPortFree || hasNextLock) {
        if (hasNextLock) {
            console.log("Detected an existing Next.js dev-server lock for this frontend. Waiting for http://localhost:3000...");
        }
        if (await frontendResponds(defaultOrigin, 45)) {
            frontendOrigin = defaultOrigin;
            return { origin: defaultOrigin, port: "3000", reuse: true };
        }
        if (hasNextLock) {
            frontendOrigin = defaultOrigin;
            console.warn("Next.js dev lock is present but /workspace is not ready yet. Reusing http://localhost:3000 instead of starting a second server.");
            return { origin: defaultOrigin, port: "3000", reuse: true, pending: true };
        }
    }

    return null;
}

async function resolveFrontendOrigin() {
    if (process.env.NEXUS_FRONTEND_URL) {
        frontendOrigin = process.env.NEXUS_FRONTEND_URL;
        return { origin: frontendOrigin, port: new URL(frontendOrigin).port || "3000", reuse: await frontendResponds(frontendOrigin) };
    }

    if (shouldUseHostedControlPlane()) {
        frontendOrigin = PACKAGED_FRONTEND_URL;
        return { origin: frontendOrigin, port: new URL(frontendOrigin).port || "443", reuse: true };
    }

    const rootDir = findRepoRoot();
    const frontendDir = path.join(rootDir, "frontend");
    const existingNext = await detectExistingNextFrontend(frontendDir);
    if (existingNext) return existingNext;

    for (let port = 3000; port <= 3010; port += 1) {
        const origin = `http://localhost:${port}`;
        if (await frontendResponds(origin)) {
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
    const safeRoute = sanitizeDesktopCodeRoute(route);
    windowRef.loadURL(safeJoinUrl(frontendOrigin, safeRoute));
}

async function resolveInitialRoute() {
    const args = process.argv.slice(1);
    const explicitFolder = args.find((arg) => arg.startsWith("--folder="))?.slice("--folder=".length);
    const folderArg = explicitFolder || args.find((arg) => {
        if (!arg || arg === "." || arg.startsWith("-") || !path.isAbsolute(arg)) return false;
        const resolved = path.resolve(arg);
        if (resolved === path.resolve(__dirname) || resolved === path.resolve(app.getAppPath())) return false;
        return fs.existsSync(resolved) && fs.statSync(resolved).isDirectory();
    });
    
    if (folderArg) {
        console.log(`CLI Folder argument detected: ${folderArg}`);
        try {
            const response = await fetch("http://127.0.0.1:8003/api/v1/code/sessions/import-local", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "x-user-id": "00000000-0000-0000-0000-000000000000"
                },
                body: JSON.stringify({ local_path: folderArg })
            });
            if (response.ok) {
                const data = await response.json();
                console.log(`CLI Import session created: ${data.id}`);
                return `/workspace?session_id=${data.id}`;
            }
        } catch (e) {
            console.error("Failed to call local-import API for CLI folder:", e);
        }
    }
    return DEFAULT_ROUTE;
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

    throw new Error("Could not find Arceus repo root. Set NEXUS_REPO_ROOT to the folder that contains backend and frontend.");
}

function tryFindRepoRoot() {
    try {
        return findRepoRoot();
    } catch {
        return null;
    }
}

function shouldUseHostedControlPlane() {
    return !isDev && process.env.NEXUS_FORCE_LOCAL_SERVICES !== "true";
}

function logDesktopEvent(message, detail = "") {
    const line = `[${new Date().toISOString()}] ${message}${detail ? ` ${detail}` : ""}\n`;
    try {
        const logFile = path.join(app.getPath("userData"), "arceus-desktop.log");
        fs.mkdirSync(path.dirname(logFile), { recursive: true });
        fs.appendFileSync(logFile, line, "utf8");
    } catch {
        // Best-effort diagnostics only.
    }
    console.log(message, detail);
}

function attachServiceLogging(childProcess, label) {
    const logChunk = (streamName, data) => {
        const text = Buffer.isBuffer(data) ? data.toString("utf8") : String(data || "");
        if (!text.trim()) return;
        const lines = text.split(/\r?\n/).filter(Boolean);
        for (const line of lines.slice(-40)) {
            const output = line.length > 4000 ? `${line.slice(0, 4000)}...` : line;
            if (streamName === "stderr") {
                console.error(`[${label}] stderr: ${output}`);
            } else {
                console.log(`[${label}] stdout: ${output}`);
            }
        }
    };

    childProcess.stdout?.on?.("data", (data) => logChunk("stdout", data));
    childProcess.stderr?.on?.("data", (data) => logChunk("stderr", data));
    childProcess.stdout?.on?.("error", (error) => {
        if (error?.code !== "EPIPE") console.error(`[${label}] stdout stream error: ${error.message}`);
    });
    childProcess.stderr?.on?.("error", (error) => {
        if (error?.code !== "EPIPE") console.error(`[${label}] stderr stream error: ${error.message}`);
    });
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
        return true;
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

    attachServiceLogging(p, serviceName);

    backendProcesses.push(p);
    console.log(`Started backend service: ${serviceName} on port ${port}`);

    const ready = await serviceResponds(port, 90);
    if (!ready) {
        console.error(`${serviceName} did not become ready on port ${port}. Check the logs above.`);
    }
    return ready;
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

    attachServiceLogging(frontendProcess, "Frontend");

    console.log(`Started Next.js frontend developer server at ${resolved.origin}.`);
    const startupResult = await Promise.race([
        frontendResponds(resolved.origin, 90).then((ready) => ({ ready })),
        new Promise((resolve) => {
            frontendProcess.once("exit", (code, signal) => resolve({ ready: false, code, signal }));
        })
    ]);

    if (startupResult.ready) {
        return;
    }

    const fallback = await detectExistingNextFrontend(frontendDir);
    if (fallback) {
        console.log(`Falling back to existing Next.js frontend at ${fallback.origin}.`);
        return;
    }

    console.error(
        `Next.js frontend did not become ready at ${resolved.origin}.` +
        (startupResult.code !== undefined ? ` Process exited with code ${startupResult.code}.` : "")
    );
}

function createLauncherWindow() {
    launcherWindow = new BrowserWindow({
        width: 600,
        height: 160,
        title: "Arceus Code Quick Open",
        frame: false,
        resizable: false,
        show: false,
        alwaysOnTop: true,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: true,
            webSecurity: true,
            allowRunningInsecureContent: false,
            preload: path.join(__dirname, "preload.js")
        },
        backgroundColor: "#0d0e12"
    });

    launcherWindow.setMenuBarVisibility(false);
    installWindowSecurityPolicy(launcherWindow);

    loadFrontendRoute(launcherWindow, "/workspace");

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
        title: "Arceus Code",
        frame: false, // Frameless design for custom titles
        transparent: false,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: true,
            webSecurity: true,
            allowRunningInsecureContent: false,
            preload: path.join(__dirname, "preload.js")
        },
        backgroundColor: "#0d0e12"
    });

    mainWindow.setMenuBarVisibility(false);
    installWindowSecurityPolicy(mainWindow);

    resolveInitialRoute().then((route) => {
        loadFrontendRoute(mainWindow, route);
    });

    mainWindow.on("closed", () => {
        mainWindow = null;
    });

    const initialUrl = process.argv.find((arg) => arg.startsWith("arceus://"));
    if (initialUrl) {
        mainWindow.webContents.once("dom-ready", () => {
            handleDeepLink(initialUrl);
        });
    }
}

function installWindowSecurityPolicy(windowRef) {
    if (!windowRef) return;
    const csp = [
        "default-src 'self' http://localhost:* http://127.0.0.1:* https://frontend-production-fbde.up.railway.app",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: http://localhost:* http://127.0.0.1:* https://frontend-production-fbde.up.railway.app",
        "style-src 'self' 'unsafe-inline' http://localhost:* http://127.0.0.1:* https://frontend-production-fbde.up.railway.app",
        "img-src 'self' data: blob: http://localhost:* http://127.0.0.1:* https:",
        "font-src 'self' data: http://localhost:* http://127.0.0.1:* https://frontend-production-fbde.up.railway.app",
        "connect-src 'self' http://localhost:* http://127.0.0.1:* ws://localhost:* ws://127.0.0.1:* https: wss:",
        "object-src 'none'",
        "frame-src 'self' http://localhost:* http://127.0.0.1:* https://frontend-production-fbde.up.railway.app",
        "base-uri 'self'"
    ].join("; ");
    windowRef.webContents.session.webRequest.onHeadersReceived((details, callback) => {
        callback({
            responseHeaders: {
                ...details.responseHeaders,
                "Content-Security-Policy": [csp],
                "X-Content-Type-Options": ["nosniff"]
            }
        });
    });
    windowRef.webContents.setWindowOpenHandler(({ url }) => {
        const frontend = new URL(frontendOrigin);
        const packaged = new URL(PACKAGED_FRONTEND_URL);
        const allowedHosts = new Set([frontend.host, packaged.host, "localhost:3000", "127.0.0.1:3000"]);
        if (isAllowedExternalUrl(url, allowedHosts)) {
            shell.openExternal(url).catch(() => {});
        }
        return { action: "deny" };
    });
    windowRef.webContents.on("will-navigate", (event, url) => {
        try {
            const target = new URL(url);
            const frontend = new URL(frontendOrigin);
            const packaged = new URL(PACKAGED_FRONTEND_URL);
            const allowedHosts = new Set([frontend.host, packaged.host, "localhost:3000", "127.0.0.1:3000"]);
            if (!allowedHosts.has(target.host)) {
                event.preventDefault();
                shell.openExternal(url).catch(() => {});
            }
        } catch {
            event.preventDefault();
        }
    });
    windowRef.webContents.session.setPermissionRequestHandler((_webContents, _permission, callback) => {
        callback(false);
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

ipcMain.handle("workspace.open", async (_event, request = {}) => {
    const { requestId, payload } = unwrapIpcPayload([request]);
    try {
        let selectedPath = payload?.rootPath;
        if (!selectedPath) {
            if (!mainWindow) throw new Error("Main window is not ready.");
            const result = await dialog.showOpenDialog(mainWindow, { properties: ["openDirectory"] });
            if (result.canceled) return ipcOk(requestId, null);
            selectedPath = result.filePaths[0];
        }
        const workspace = await inspectWorkspace(selectedPath);
        if (payload?.trusted === true) {
            workspace.trusted = true;
            trustedWorkspaces.set(workspace.rootPath, workspace);
        }
        logDesktopEvent("WORKSPACE_OPENED", workspace.rootPath);
        return ipcOk(requestId, workspace);
    } catch (error) {
        return ipcFail(requestId, desktopError("INVALID_REQUEST", error?.message || "Could not open workspace.", true));
    }
});

ipcMain.handle("workspace.trust", async (_event, request = {}) => {
    const { requestId, payload } = unwrapIpcPayload([request]);
    try {
        const workspace = await inspectWorkspace(payload?.rootPath);
        workspace.trusted = Boolean(payload?.trusted);
        trustedWorkspaces.set(workspace.rootPath, workspace);
        logDesktopEvent(workspace.trusted ? "WORKSPACE_TRUST_GRANTED" : "WORKSPACE_TRUST_REVOKED", workspace.rootPath);
        return ipcOk(requestId, workspace);
    } catch (error) {
        return ipcFail(requestId, desktopError("INVALID_REQUEST", error?.message || "Could not update workspace trust."));
    }
});

ipcMain.handle("workspace.discoverTasks", async (_event, request = {}) => {
    const { requestId, payload } = unwrapIpcPayload([request]);
    try {
        const { root } = await resolveWorkspacePathStrict(payload?.rootPath);
        const tasks = discoverWorkspaceTasks(root);
        return ipcOk(requestId, { rootPath: root, tasks });
    } catch (error) {
        return ipcFail(requestId, desktopError("INVALID_REQUEST", error?.message || "Could not discover workspace tasks.", true));
    }
});

ipcMain.handle("workspace-read-directory-tree", async (_event, rootPath) => {
    return readWorkspaceTree(rootPath);
});

ipcMain.handle("filesystem.readFile", async (_event, request = {}) => {
    const { requestId, payload } = unwrapIpcPayload([request]);
    try {
        const { target, relative } = await resolveWorkspacePathStrict(payload?.rootPath, payload?.relativePath);
        const stat = await fs.promises.stat(target);
        if (!stat.isFile()) throw new Error("Selected path is not a file.");
        if (stat.size > WORKSPACE_MAX_FILE_BYTES) throw new Error("File is too large for inline editing.");
        const buffer = await fs.promises.readFile(target);
        if (buffer.includes(0)) throw new Error("Binary files are not supported.");
        return ipcOk(requestId, { path: relative, content: buffer.toString("utf8"), size_bytes: stat.size });
    } catch (error) {
        return ipcFail(requestId, desktopError("FILE_NOT_FOUND", error?.message || "Could not read file.", true));
    }
});

ipcMain.handle("workspace-read-file", async (_event, rootPath, relativePath) => {
    const { target, relative } = await resolveWorkspacePathStrict(rootPath, relativePath);
    const stat = await fs.promises.stat(target);
    if (!stat.isFile()) throw new Error("Selected path is not a file.");
    if (stat.size > WORKSPACE_MAX_FILE_BYTES) throw new Error("File is too large for inline editing.");
    const buffer = await fs.promises.readFile(target);
    if (buffer.includes(0)) throw new Error("Binary files are not supported.");
    return { path: relative, content: buffer.toString("utf8"), size_bytes: stat.size };
});

ipcMain.handle("filesystem.writeFile", async (_event, request = {}) => {
    const { requestId, payload } = unwrapIpcPayload([request]);
    try {
        const { target, relative } = await resolveWorkspacePathStrict(payload?.rootPath, payload?.relativePath);
        const data = Buffer.from(String(payload?.content ?? ""), "utf8");
        if (data.length > WORKSPACE_MAX_FILE_BYTES) throw new Error("File is too large for local write.");
        await atomicWriteFile(target, data);
        return ipcOk(requestId, { path: relative, size_bytes: data.length, atomic: true });
    } catch (error) {
        return ipcFail(requestId, desktopError("INVALID_REQUEST", error?.message || "Could not write file."));
    }
});

ipcMain.handle("workspace-write-file", async (_event, rootPath, relativePath, content = "") => {
    const { target, relative } = await resolveWorkspacePathStrict(rootPath, relativePath);
    const data = Buffer.from(String(content), "utf8");
    if (data.length > WORKSPACE_MAX_FILE_BYTES) throw new Error("File is too large for local write.");
    await atomicWriteFile(target, data);
    return { path: relative, size_bytes: data.length, atomic: true };
});

ipcMain.handle("workspace-create-item", async (_event, rootPath, relativePath, type = "file", content = "") => {
    const { target, relative } = await resolveWorkspacePathStrict(rootPath, relativePath);
    if (type === "folder") {
        await fs.promises.mkdir(target, { recursive: true });
        return { path: relative, type: "folder" };
    }
    const data = Buffer.from(String(content), "utf8");
    if (data.length > WORKSPACE_MAX_FILE_BYTES) throw new Error("File is too large for local create.");
    await fs.promises.mkdir(path.dirname(target), { recursive: true });
    await fs.promises.writeFile(target, data, { flag: "wx" });
    return { path: relative, type: "file", size_bytes: data.length };
});

ipcMain.handle("workspace-rename-item", async (_event, rootPath, fromRelativePath, toRelativePath) => {
    const from = await resolveWorkspacePathStrict(rootPath, fromRelativePath);
    const to = await resolveWorkspacePathStrict(rootPath, toRelativePath);
    await fs.promises.mkdir(path.dirname(to.target), { recursive: true });
    await fs.promises.rename(from.target, to.target);
    return { from: from.relative, to: to.relative };
});

ipcMain.handle("workspace-delete-item", async (_event, rootPath, relativePath) => {
    const { target, relative } = await resolveWorkspacePathStrict(rootPath, relativePath);
    await fs.promises.rm(target, { recursive: true, force: false });
    return { path: relative, deleted: true };
});

ipcMain.handle("workspace-reveal-item", async (_event, rootPath, relativePath) => {
    const { target, relative } = await resolveWorkspacePathStrict(rootPath, relativePath);
    shell.showItemInFolder(target);
    return { path: relative, revealed: true };
});

function findExecutableOnPath(name) {
    const pathValue = process.env.PATH || "";
    const extensions = process.platform === "win32"
        ? (process.env.PATHEXT || ".EXE;.CMD;.BAT").split(";")
        : [""];
    const requestedExt = path.extname(name);
    for (const directory of pathValue.split(path.delimiter)) {
        if (!directory) continue;
        const candidates = requestedExt ? [path.join(directory, name)] : extensions.map((ext) => path.join(directory, `${name}${ext}`));
        for (const candidate of candidates) {
            if (fs.existsSync(candidate)) return candidate;
        }
    }
    return "";
}

function terminalShell(profile) {
    const requested = String(profile || "").toLowerCase();
    if (process.platform === "win32") {
        if (requested === "cmd") return process.env.ComSpec || "cmd.exe";
        if (requested === "pwsh") return findExecutableOnPath("pwsh") || "powershell.exe";
        if (requested === "bash") return findExecutableOnPath("bash") || "powershell.exe";
        if (requested === "sh") return findExecutableOnPath("sh") || "powershell.exe";
        if (requested === "zsh") return findExecutableOnPath("zsh") || "powershell.exe";
        return "powershell.exe";
    }
    const shells = {
        bash: "/bin/bash",
        zsh: "/bin/zsh",
        sh: "/bin/sh",
        pwsh: "pwsh",
        powershell: "pwsh"
    };
    return shells[requested] || process.env.SHELL || "/bin/sh";
}

function terminalShellArgs(shellPath) {
    const basename = path.basename(String(shellPath || "")).toLowerCase();
    if (process.platform === "win32" && (basename === "powershell.exe" || basename === "pwsh.exe")) {
        return ["-NoLogo", "-NoProfile", "-NoExit"];
    }
    if (process.platform === "win32" && basename === "cmd.exe") {
        return ["/Q"];
    }
    return [];
}

function emitTerminalData(id, data) {
    const session = terminalSessions.get(id);
    const seq = session ? Number(session.streamSeq || 0) + 1 : 1;
    if (session) {
        session.streamSeq = seq;
        session.updatedAt = new Date().toISOString();
        terminalSessions.set(id, session);
    }
    const payload = { id, seq, data: String(data || ""), timestamp: new Date().toISOString() };
    if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send("terminal-data", payload);
    }
}

function emitTerminalExit(id, code, signal) {
    const session = terminalSessions.get(id);
    if (session) {
        session.status = "exited";
        session.exitCode = code;
        session.signal = signal;
        session.updatedAt = new Date().toISOString();
        terminalSessions.set(id, session);
    }
    if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send("terminal-exit", { id, code, signal, timestamp: new Date().toISOString() });
    }
}

async function createTerminalSession(rootPath, options = {}) {
    const { root } = await resolveWorkspacePathStrict(rootPath);
    const id = `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const cols = Number(options.cols || 100);
    const rows = Number(options.rows || 28);
    const shell = terminalShell(options.shell);
    const createdAt = new Date().toISOString();
    const session = {
        id,
        cwd: root,
        status: "active",
        shell,
        title: options.title || path.basename(shell),
        createdBy: options.createdBy || "user",
        missionId: options.missionId || null,
        agentId: options.agentId || null,
        history: [],
        logs: [],
        streamSeq: 0,
        backend: nodePty ? "node-pty" : "child-process",
        created_at: createdAt,
        updated_at: createdAt
    };

    if (nodePty) {
        const ptyProcess = nodePty.spawn(shell, [], {
            name: "xterm-256color",
            cols,
            rows,
            cwd: root,
            env: process.env
        });
        session.process = ptyProcess;
        ptyProcess.onData((data) => {
            const current = terminalSessions.get(id);
            if (current) {
                current.logs.push({ status: "stream", output_excerpt: String(data).slice(-4000), updated_at: new Date().toISOString() });
                current.logs = current.logs.slice(-200);
                current.updated_at = new Date().toISOString();
                terminalSessions.set(id, current);
            }
            emitTerminalData(id, data);
        });
        ptyProcess.onExit(({ exitCode, signal }) => emitTerminalExit(id, exitCode, signal));
    } else {
        const child = spawn(shell, terminalShellArgs(shell), {
            cwd: root,
            env: process.env,
            shell: false,
            stdio: ["pipe", "pipe", "pipe"]
        });
        session.process = child;
        emitTerminalData(id, "node-pty is unavailable. Running in command-bar fallback mode.\r\n");
        child.stdout.on("data", (data) => emitTerminalData(id, data));
        child.stderr.on("data", (data) => emitTerminalData(id, data));
        child.on("close", (code, signal) => emitTerminalExit(id, code, signal));
    }

    terminalSessions.set(id, session);
    return {
        id,
        status: session.status,
        cwd: session.cwd,
        shell: session.shell,
        title: session.title,
        createdBy: session.createdBy,
        missionId: session.missionId,
        agentId: session.agentId,
        history: session.history,
        logs: session.logs,
        backend: session.backend,
        created_at: session.created_at,
        updated_at: session.updated_at
    };
}

ipcMain.handle("terminal-create", async (_event, rootPath, options = {}) => {
    return createTerminalSession(rootPath, options);
});

ipcMain.handle("terminal.create", async (_event, request = {}) => {
    const { requestId, payload, initiatedBy, missionId, agentId } = unwrapIpcPayload([request]);
    try {
        const rootPath = payload?.rootPath;
        const options = {
            ...(payload?.options || {}),
            shell: payload?.shell || payload?.options?.shell,
            title: payload?.title,
            createdBy: payload?.createdBy || initiatedBy || "user",
            missionId: payload?.missionId || missionId,
            agentId: payload?.agentId || agentId,
            cols: payload?.cols,
            rows: payload?.rows
        };
        const legacyResult = await createTerminalSession(rootPath, options);
        return ipcOk(requestId, legacyResult);
    } catch (error) {
        return ipcFail(requestId, desktopError("PROCESS_FAILED", error?.message || "Could not create terminal.", true));
    }
});

ipcMain.handle("terminal-input", async (_event, terminalId, input = "", options = {}) => {
    const session = terminalSessions.get(terminalId);
    if (!session || !session.process) throw new Error("Terminal session not found.");
    const text = String(input || "");
    if (!text) return { id: terminalId, ignored: true };
    const raw = Boolean(options && options.raw);
    if (!raw && text.trim()) session.history.push(text.trim());
    session.updated_at = new Date().toISOString();
    terminalSessions.set(terminalId, session);
    if (nodePty && typeof session.process.write === "function") {
        session.process.write(raw ? text : (text.endsWith("\r") || text.endsWith("\n") ? text : `${text}\r`));
    } else if (session.process.stdin?.writable) {
        session.process.stdin.write(raw ? text : (text.endsWith("\n") ? text : `${text}\n`));
    }
    return { id: terminalId, status: session.status, cwd: session.cwd, history: session.history, logs: session.logs, backend: session.backend };
});

ipcMain.handle("terminal.sendInput", async (_event, request = {}) => {
    const { requestId, payload } = unwrapIpcPayload([request]);
    try {
        const terminalId = payload?.terminalId;
        const session = terminalSessions.get(terminalId);
        if (!session || !session.process) throw new Error("Terminal session not found.");
        const text = String(payload?.input || "");
        if (!text) return ipcOk(requestId, { id: terminalId, ignored: true });
        const raw = Boolean(payload?.raw);
        if (!raw && text.trim()) session.history.push(text.trim());
        session.updated_at = new Date().toISOString();
        terminalSessions.set(terminalId, session);
        if (nodePty && typeof session.process.write === "function") {
            session.process.write(raw ? text : (text.endsWith("\r") || text.endsWith("\n") ? text : `${text}\r`));
        } else if (session.process.stdin?.writable) {
            session.process.stdin.write(raw ? text : (text.endsWith("\n") ? text : `${text}\n`));
        }
        return ipcOk(requestId, { id: terminalId, status: session.status, cwd: session.cwd, history: session.history, logs: session.logs, backend: session.backend });
    } catch (error) {
        return ipcFail(requestId, desktopError("PROCESS_FAILED", error?.message || "Could not send terminal input.", true));
    }
});

ipcMain.handle("terminal-resize", async (_event, terminalId, cols, rows) => {
    const session = terminalSessions.get(terminalId);
    if (!session) throw new Error("Terminal session not found.");
    if (nodePty && typeof session.process?.resize === "function") {
        session.process.resize(Number(cols || 100), Number(rows || 28));
    }
    return { id: terminalId, resized: true };
});

ipcMain.handle("terminal-kill", async (_event, terminalId) => {
    const session = terminalSessions.get(terminalId);
    if (!session) return { id: terminalId, status: "missing" };
    try {
        if (nodePty && typeof session.process?.kill === "function") {
            session.process.kill();
        } else if (session.process?.pid) {
            if (process.platform === "win32") exec(`taskkill /pid ${session.process.pid} /t /f`);
            else session.process.kill("SIGTERM");
        }
    } catch (error) {
        console.error("Failed to kill terminal:", error);
    }
    session.status = "killed";
    session.updated_at = new Date().toISOString();
    terminalSessions.set(terminalId, session);
    emitTerminalExit(terminalId, null, "killed");
    return { id: terminalId, status: "killed", cwd: session.cwd, history: session.history, logs: session.logs, backend: session.backend };
});

ipcMain.handle("terminal.kill", async (_event, request = {}) => {
    const { requestId, payload } = unwrapIpcPayload([request]);
    try {
        const terminalId = payload?.terminalId;
        const session = terminalSessions.get(terminalId);
        if (!session) return ipcOk(requestId, { id: terminalId, status: "missing" });
        try {
            if (nodePty && typeof session.process?.kill === "function") {
                session.process.kill();
            } else if (session.process?.pid) {
                if (process.platform === "win32") exec(`taskkill /pid ${session.process.pid} /t /f`);
                else session.process.kill("SIGTERM");
            }
        } catch (error) {
            console.error("Failed to kill terminal:", error);
        }
        session.status = "killed";
        session.updated_at = new Date().toISOString();
        terminalSessions.set(terminalId, session);
        emitTerminalExit(terminalId, null, "killed");
        return ipcOk(requestId, { id: terminalId, status: "killed", cwd: session.cwd, history: session.history, logs: session.logs, backend: session.backend });
    } catch (error) {
        return ipcFail(requestId, desktopError("PROCESS_FAILED", error?.message || "Could not kill terminal."));
    }
});

function flushDirectoryChanges() {
    if (!mainWindow || mainWindow.isDestroyed() || dirWatcherBatch.length === 0) {
        dirWatcherBatch = [];
        return;
    }
    const changes = dirWatcherBatch;
    dirWatcherBatch = [];
    mainWindow.webContents.send("directory-changed", {
        event: "batch",
        rootPath: dirWatcherRoot,
        changes,
        timestamp: new Date().toISOString()
    });
}

async function closeDirectoryWatcher() {
    if (dirWatcher) {
        try {
            await dirWatcher.close();
        } catch (e) {
            console.error("Failed to close existing watcher:", e);
        }
        dirWatcher = null;
        dirWatcherRoot = "";
    }
}

ipcMain.handle("watch-directory-stop", async () => {
    await closeDirectoryWatcher();
    return { stopped: true };
});

ipcMain.on("watch-directory", async (event, dirPath) => {
    await closeDirectoryWatcher();
    try {
        const chokidarModule = await import("chokidar");
        const chokidar = chokidarModule.default || chokidarModule;
        const root = path.resolve(dirPath);
        dirWatcherRoot = root;
        dirWatcher = chokidar.watch(root, {
            ignored: (filePath) => {
                const rel = path.relative(root, filePath).replace(/\\/g, "/");
                return Boolean(rel && isIgnoredWorkspacePath(rel));
            },
            persistent: true,
            ignoreInitial: false,
            awaitWriteFinish: {
                stabilityThreshold: 80,
                pollInterval: 20
            }
        });
        
        const notifyWatchError = (error) => {
            const message = error?.message || String(error || "Folder watcher failed.");
            console.error("Folder watch error:", message);
            event.sender.send("folder-watch-error", {
                rootPath: root,
                message,
                timestamp: new Date().toISOString()
            });
        };

        const sendChange = (changeEvent, filepath) => {
            const relPath = path.relative(root, filepath).replace(/\\/g, "/");
            if (!relPath || isIgnoredWorkspacePath(relPath)) return;
            dirWatcherBatch.push({
                event: changeEvent,
                path: relPath,
                absolutePath: filepath
            });
            if (dirWatcherTimer) clearTimeout(dirWatcherTimer);
            dirWatcherTimer = setTimeout(flushDirectoryChanges, 50);
        };
        
        dirWatcher
            .on("add", (filepath) => sendChange("add", filepath))
            .on("change", (filepath) => sendChange("change", filepath))
            .on("unlink", (filepath) => sendChange("unlink", filepath))
            .on("addDir", (filepath) => sendChange("addDir", filepath))
            .on("unlinkDir", (filepath) => sendChange("unlinkDir", filepath))
            .on("error", notifyWatchError);
            
        console.log(`Started watching directory: ${root}`);
    } catch (error) {
        event.sender.send("folder-watch-error", {
            rootPath: dirPath,
            message: error?.message || String(error || "Folder watcher failed."),
            timestamp: new Date().toISOString()
        });
    }
});

app.whenReady().then(async () => {
    configureAutoUpdater();

    if (shouldUseHostedControlPlane()) {
        frontendOrigin = PACKAGED_FRONTEND_URL;
        logDesktopEvent("Packaged Arceus install using hosted control plane:", frontendOrigin);
        createWindow();
        createLauncherWindow();
        checkForAppUpdates();

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
        return;
    }

    // 1. Launch local infrastructure required by the FastAPI services.
    const dependenciesReady = await startLocalDependencies();

    // 2. Launch local backend microservices after Postgres/Redis are reachable.
    if (dependenciesReady) {
        await startBackendService("auth-service", "services.auth.main:app", 8001);
        await startBackendService("goals-service", "services.goals.main:app", 8002);
        await startBackendService("agent-service", "services.agent.main:app", 8003);
    } else {
        console.error("Database startup failed. Backend services were not launched to avoid repeated connection errors.");
    }

    // 3. Launch Next.js frontend
    await startFrontendService();

    // 4. Create native app UI window
    createWindow();
    createLauncherWindow();
    checkForAppUpdates();

    // 5. Register system-wide global shortcut to toggle launcher visibility
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
    closeDirectoryWatcher().catch(() => {});
    if (managedPostgres?.pgCtl && managedPostgres?.dataDir) {
        try {
            const stopProcess = spawn(managedPostgres.pgCtl, ["stop", "-D", managedPostgres.dataDir, "-m", "fast"], {
                detached: true,
                stdio: "ignore",
                shell: false
            });
            stopProcess.unref();
        } catch (error) {
            console.error(`Failed to stop Arceus local PostgreSQL: ${error.message}`);
        }
    }
});

app.on("window-all-closed", () => {
    // Terminate all background processes on exit
    console.log("Shutting down local Arceus services...");
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
