const { spawn } = require("child_process");
const path = require("path");

const DEFAULT_TIMEOUT_MS = 60_000;
const MAX_OUTPUT_CHARS = 40_000;
const activeCommands = new Map();

const ALLOWED_COMMANDS = [
    { command: "npm", prefixes: [["run", "test"], ["run", "lint"], ["run", "build"], ["test"]] },
    { command: "pytest", prefixes: [[]] },
    { command: "python", prefixes: [["-m", "compileall"]] },
    { command: "git", prefixes: [["status"]] },
    { command: "cargo", prefixes: [["test"]] },
    { command: "go", prefixes: [["test"]] },
];

const NEEDS_APPROVAL_COMMANDS = new Set(["git push", "docker compose down", "rm -rf", "del /s", "format", "shutdown", "reboot"]);
const SHELL_META = /[|&;<>()`]/;

function normalizeCommand(input = {}) {
    const command = String(input.command || "").trim();
    const args = Array.isArray(input.args) ? input.args.map((arg) => String(arg)) : [];
    if (!command) throw new Error("Command is required.");
    if (SHELL_META.test(command) || args.some((arg) => SHELL_META.test(arg))) {
        throw new Error("Shell metacharacters are not allowed in command runtime.");
    }
    return { command, args };
}

function isPrefix(args, prefix) {
    if (prefix.length === 0) return true;
    if (args.length < prefix.length) return false;
    return prefix.every((value, index) => args[index] === value);
}

function validateCommand(input = {}) {
    const normalized = normalizeCommand(input);
    const printable = [normalized.command, ...normalized.args].join(" ");
    if ([...NEEDS_APPROVAL_COMMANDS].some((needle) => printable.toLowerCase().startsWith(needle))) {
        return { ok: false, reason: "approval_required", message: "Command requires explicit approval." };
    }
    const basename = path.basename(normalized.command).replace(/\.(cmd|exe|bat)$/i, "");
    const allowed = ALLOWED_COMMANDS.some((entry) => {
        if (entry.command !== basename) return false;
        return entry.prefixes.some((prefix) => isPrefix(normalized.args, prefix));
    });
    if (!allowed) {
        return { ok: false, reason: "policy_denied", message: "Command is not in the safe allowlist." };
    }
    return { ok: true, ...normalized };
}

function truncate(value) {
    const text = String(value || "");
    if (text.length <= MAX_OUTPUT_CHARS) return text;
    return `${text.slice(0, MAX_OUTPUT_CHARS)}\n[truncated ${text.length - MAX_OUTPUT_CHARS} chars]`;
}

function runCommand(input = {}) {
    const validation = validateCommand(input);
    if (!validation.ok) {
        const error = new Error(validation.message);
        error.code = validation.reason;
        throw error;
    }
    const cwd = input.cwd ? path.resolve(String(input.cwd)) : process.cwd();
    const timeoutMs = Math.max(1_000, Math.min(Number(input.timeout_ms || DEFAULT_TIMEOUT_MS), 10 * 60_000));
    const started = Date.now();
    const commandId = input.command_id || (cryptoRandomId());
    return new Promise((resolve) => {
        const child = spawn(validation.command, validation.args, {
            cwd,
            env: process.env,
            shell: false,
            windowsHide: true,
        });
        activeCommands.set(commandId, child);
        let stdout = "";
        let stderr = "";
        let timedOut = false;
        const timer = setTimeout(() => {
            timedOut = true;
            try {
                child.kill("SIGTERM");
            } catch {
                // Process may have already exited.
            }
        }, timeoutMs);
        child.stdout?.on("data", (data) => {
            stdout += data.toString();
        });
        child.stderr?.on("data", (data) => {
            stderr += data.toString();
        });
        child.once("error", (error) => {
            clearTimeout(timer);
            activeCommands.delete(commandId);
            resolve({
                command_id: commandId,
                command: validation.command,
                args: validation.args,
                cwd,
                exit_code: null,
                timed_out: timedOut,
                stdout: truncate(stdout),
                stderr: truncate(stderr || error.message),
                duration_ms: Date.now() - started,
            });
        });
        child.once("close", (code, signal) => {
            clearTimeout(timer);
            activeCommands.delete(commandId);
            resolve({
                command_id: commandId,
                command: validation.command,
                args: validation.args,
                cwd,
                exit_code: timedOut ? null : code,
                signal,
                timed_out: timedOut,
                stdout: truncate(stdout),
                stderr: truncate(stderr),
                duration_ms: Date.now() - started,
            });
        });
    });
}

function cryptoRandomId() {
    return `cmd_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function cancelCommand(commandId) {
    const child = activeCommands.get(commandId);
    if (!child) {
        return { ok: false, message: "Command is not running." };
    }
    try {
        child.kill("SIGTERM");
        activeCommands.delete(commandId);
        return { ok: true, command_id: commandId, cancelled: true };
    } catch (error) {
        return { ok: false, command_id: commandId, message: error.message || "Could not cancel command." };
    }
}

module.exports = {
    cancelCommand,
    validateCommand,
    runCommand,
};
