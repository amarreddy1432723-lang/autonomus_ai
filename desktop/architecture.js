const path = require("path");

const DESKTOP_ERROR_CODES = {
    PATH_OUTSIDE_WORKSPACE: "PATH_OUTSIDE_WORKSPACE",
    FILE_NOT_FOUND: "FILE_NOT_FOUND",
    PERMISSION_DENIED: "PERMISSION_DENIED",
    PROCESS_FAILED: "PROCESS_FAILED",
    GIT_ERROR: "GIT_ERROR",
    WORKSPACE_NOT_OPEN: "WORKSPACE_NOT_OPEN",
    INVALID_REQUEST: "INVALID_REQUEST",
    UPDATE_ERROR: "UPDATE_ERROR",
    LOCAL_MODEL_ERROR: "LOCAL_MODEL_ERROR",
    UNKNOWN: "UNKNOWN"
};

const DESKTOP_CAPABILITIES = Object.freeze({
    fileSystem: true,
    terminal: true,
    git: true,
    localModels: true,
    systemNotifications: true,
    autoUpdate: true
});

function desktopError(code, message, retryable = false, details = {}) {
    return {
        code: DESKTOP_ERROR_CODES[code] || DESKTOP_ERROR_CODES.UNKNOWN,
        message,
        retryable,
        details: redactDetails(details)
    };
}

function ipcOk(requestId, result) {
    return { requestId: requestId || "", ok: true, result };
}

function ipcFail(requestId, error) {
    return {
        requestId: requestId || "",
        ok: false,
        error: error && error.code ? error : desktopError("UNKNOWN", error?.message || "Desktop operation failed.")
    };
}

function unwrapIpcPayload(args) {
    const first = args[0];
    if (first && typeof first === "object" && Object.prototype.hasOwnProperty.call(first, "payload")) {
        return {
            requestId: String(first.requestId || ""),
            payload: first.payload || {},
            initiatedBy: first.initiatedBy || "user",
            missionId: first.missionId,
            agentId: first.agentId
        };
    }
    return { requestId: "", payload: null, initiatedBy: "user" };
}

function redactDetails(details = {}) {
    const blocked = /(token|secret|password|authorization|key)/i;
    return Object.fromEntries(
        Object.entries(details || {}).map(([key, value]) => [
            key,
            blocked.test(key) ? "[REDACTED]" : value
        ])
    );
}

function safeJoinUrl(origin, route) {
    const base = new URL(origin);
    const target = new URL(route || "/", base);
    return target.toString();
}

function isAllowedExternalUrl(targetUrl, allowedHosts) {
    try {
        const parsed = new URL(String(targetUrl || ""));
        return ["http:", "https:"].includes(parsed.protocol) && allowedHosts.has(parsed.host);
    } catch {
        return false;
    }
}

function workspaceIdFor(rootPath) {
    const normalized = path.resolve(rootPath || "").toLowerCase();
    let hash = 0;
    for (let i = 0; i < normalized.length; i += 1) {
        hash = ((hash << 5) - hash + normalized.charCodeAt(i)) | 0;
    }
    return `workspace_${Math.abs(hash).toString(16)}`;
}

module.exports = {
    DESKTOP_CAPABILITIES,
    DESKTOP_ERROR_CODES,
    desktopError,
    ipcFail,
    ipcOk,
    isAllowedExternalUrl,
    safeJoinUrl,
    unwrapIpcPayload,
    workspaceIdFor
};

