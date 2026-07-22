const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { cancelCommand, runCommand, validateCommand } = require("./terminal-runtime");
const { assertRepositoryAllowed, assertRepositoryRoot, isIgnoredRelativePath } = require("./repository-policy");

const MAX_READ_BYTES = 1_500_000;
const MAX_DIRECTORY_ITEMS = 2_000;
const MAX_SEARCH_RESULTS = 200;

const auditLog = [];
const rollbackSnapshots = new Map();

function nowIso() {
    return new Date().toISOString();
}

function sha256(value) {
    return crypto.createHash("sha256").update(value).digest("hex");
}

function summarize(value, limit = 500) {
    const text = typeof value === "string" ? value : JSON.stringify(value || {});
    return text.length > limit ? `${text.slice(0, limit)}...` : text;
}

function ok(data = {}) {
    return { ok: true, ...data };
}

function fail(code, message, data = {}) {
    return { ok: false, error_class: code, message, ...data };
}

function auditRecord(toolId, input, result, startedAt) {
    const record = {
        id: crypto.randomUUID ? crypto.randomUUID() : `audit_${Date.now()}_${Math.random().toString(16).slice(2)}`,
        tool: toolId,
        timestamp: nowIso(),
        duration_ms: Date.now() - startedAt,
        input_summary: summarize(input),
        output_summary: summarize(result),
        status: result.ok ? "succeeded" : "failed",
        error_class: result.error_class || null,
    };
    auditLog.push(record);
    if (auditLog.length > 1_000) auditLog.shift();
    return record;
}

function createTool(id, description, validate, execute) {
    return {
        id,
        description,
        validate,
        execute,
        audit: (input, result, startedAt) => auditRecord(id, input, result, startedAt),
    };
}

async function walkFiles(root, base = "", results = []) {
    if (results.length >= MAX_DIRECTORY_ITEMS) return results;
    const entries = await fs.promises.readdir(path.join(root, base), { withFileTypes: true });
    for (const entry of entries) {
        const rel = base ? `${base}/${entry.name}` : entry.name;
        if (isIgnoredRelativePath(rel)) continue;
        const full = path.join(root, rel);
        if (entry.isDirectory()) {
            await walkFiles(root, rel, results);
        } else if (entry.isFile()) {
            results.push(rel.replace(/\\/g, "/"));
        }
        if (results.length >= MAX_DIRECTORY_ITEMS) break;
    }
    return results;
}

function buildUnifiedDiff(relativePath, original, modified) {
    const originalLines = String(original || "").split(/\r?\n/);
    const modifiedLines = String(modified || "").split(/\r?\n/);
    const lines = [`--- a/${relativePath}`, `+++ b/${relativePath}`, `@@ -1,${originalLines.length} +1,${modifiedLines.length} @@`];
    for (const line of originalLines) lines.push(`-${line}`);
    for (const line of modifiedLines) lines.push(`+${line}`);
    return `${lines.join("\n")}\n`;
}

async function validatePatchOperation(input) {
    if (!input.repositoryRoot || !input.path || !input.operation) {
        return fail("tool_validation", "repositoryRoot, path and operation are required.");
    }
    if (["delete", "rename", "move"].includes(input.operation)) {
        return fail("review_required", "Destructive patch operations require manual review.", {
            operation: input.operation,
            review_required: true,
        });
    }
    const resolved = await assertRepositoryAllowed(input.repositoryRoot, input.path);
    if (input.operation === "folder") {
        const exists = await fs.promises.stat(resolved.target).then(() => true).catch(() => false);
        if (exists) return fail("patch_conflict", "Folder already exists.", { path: resolved.relative });
        return ok({ operation: "folder", path: resolved.relative, risk: "low", review_required: false });
    }
    if (!["create", "modify"].includes(input.operation)) {
        return fail("tool_validation", `Unsupported patch operation: ${input.operation}`);
    }
    if (typeof input.modifiedContent !== "string") {
        return fail("tool_validation", "modifiedContent is required for create and modify patch operations.");
    }
    const original = await fs.promises.readFile(resolved.target, "utf8").catch(() => null);
    if (input.operation === "create" && original !== null) {
        return fail("patch_conflict", "Target file already exists.", { path: resolved.relative });
    }
    if (input.operation === "modify" && original === null) {
        return fail("patch_conflict", "Target file is missing.", { path: resolved.relative });
    }
    if (original !== null && input.originalSha256 && sha256(original) !== input.originalSha256) {
        return fail("patch_conflict", "Original file hash does not match.", { path: resolved.relative });
    }
    return ok({
        operation: input.operation,
        path: resolved.relative,
        original_sha256: original === null ? null : sha256(original),
        modified_sha256: sha256(input.modifiedContent),
        diff: buildUnifiedDiff(resolved.relative, original || "", input.modifiedContent),
        risk: input.operation === "create" ? "low" : "medium",
        review_required: false,
    });
}

function createRollbackSnapshot(input, validated, originalContent) {
    const id = crypto.randomUUID ? crypto.randomUUID() : `rollback_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    rollbackSnapshots.set(id, {
        id,
        created_at: nowIso(),
        repositoryRoot: path.resolve(input.repositoryRoot),
        operation: validated.operation,
        path: validated.path,
        original_content: originalContent,
        original_sha256: validated.original_sha256 || null,
        modified_sha256: validated.modified_sha256 || null,
        used: false,
    });
    return id;
}

const tools = new Map();

function register(tool) {
    tools.set(tool.id, tool);
}

register(createTool(
    "read_file",
    "Read a file inside the repository.",
    (input) => {
        if (!input.repositoryRoot || !input.path) throw new Error("repositoryRoot and path are required.");
    },
    async (input) => {
        const resolved = await assertRepositoryAllowed(input.repositoryRoot, input.path);
        const stat = await fs.promises.stat(resolved.target);
        if (!stat.isFile()) return fail("tool_validation", "Path is not a file.", { path: resolved.relative });
        if (stat.size > MAX_READ_BYTES) return fail("file_too_large", "File is too large to read safely.", { path: resolved.relative, size_bytes: stat.size });
        const content = await fs.promises.readFile(resolved.target, "utf8");
        return ok({ path: resolved.relative, content, size_bytes: stat.size, sha256: sha256(content) });
    }
));

register(createTool(
    "read_directory",
    "List repository directory entries.",
    (input) => {
        if (!input.repositoryRoot) throw new Error("repositoryRoot is required.");
    },
    async (input) => {
        const resolved = await assertRepositoryAllowed(input.repositoryRoot, input.path || ".");
        const entries = await fs.promises.readdir(resolved.target, { withFileTypes: true });
        return ok({
            path: resolved.relative,
            entries: entries
                .filter((entry) => !isIgnoredRelativePath(resolved.relative === "." ? entry.name : `${resolved.relative}/${entry.name}`))
                .slice(0, MAX_DIRECTORY_ITEMS)
                .map((entry) => ({ name: entry.name, type: entry.isDirectory() ? "folder" : "file" })),
        });
    }
));

register(createTool(
    "search_repository",
    "Search text across repository files.",
    (input) => {
        if (!input.repositoryRoot || !input.query) throw new Error("repositoryRoot and query are required.");
    },
    async (input) => {
        const root = await assertRepositoryRoot(input.repositoryRoot);
        const query = String(input.query);
        const files = await walkFiles(root);
        const matches = [];
        for (const rel of files) {
            if (matches.length >= MAX_SEARCH_RESULTS) break;
            const resolved = await assertRepositoryAllowed(root, rel);
            const stat = await fs.promises.stat(resolved.target);
            if (stat.size > MAX_READ_BYTES) continue;
            const content = await fs.promises.readFile(resolved.target, "utf8").catch(() => "");
            const lines = content.split(/\r?\n/);
            lines.forEach((line, index) => {
                if (matches.length < MAX_SEARCH_RESULTS && line.toLowerCase().includes(query.toLowerCase())) {
                    matches.push({ path: rel, line: index + 1, text: line.slice(0, 300) });
                }
            });
        }
        return ok({ query, matches });
    }
));

register(createTool(
    "inspect_symbol",
    "Find functions/classes/interfaces/imports/routes by simple symbol scan.",
    (input) => {
        if (!input.repositoryRoot || !input.symbol) throw new Error("repositoryRoot and symbol are required.");
    },
    async (input) => {
        const root = await assertRepositoryRoot(input.repositoryRoot);
        const symbol = String(input.symbol);
        const files = await walkFiles(root);
        const pattern = new RegExp(`(function|class|interface|const|let|var|def|import|from|router\\.|app\\.)[^\\n]*${symbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`, "i");
        const matches = [];
        for (const rel of files) {
            if (matches.length >= MAX_SEARCH_RESULTS) break;
            const resolved = await assertRepositoryAllowed(root, rel);
            const stat = await fs.promises.stat(resolved.target);
            if (stat.size > MAX_READ_BYTES) continue;
            const content = await fs.promises.readFile(resolved.target, "utf8").catch(() => "");
            const lines = content.split(/\r?\n/);
            lines.forEach((line, index) => {
                if (matches.length < MAX_SEARCH_RESULTS && pattern.test(line)) {
                    matches.push({ path: rel, line: index + 1, text: line.trim().slice(0, 300) });
                }
            });
        }
        return ok({ symbol, matches });
    }
));

register(createTool(
    "propose_patch",
    "Create a validated patch proposal without applying it.",
    (input) => {
        if (!input.repositoryRoot || !input.path || typeof input.modifiedContent !== "string") throw new Error("repositoryRoot, path and modifiedContent are required.");
    },
    async (input) => {
        const resolved = await assertRepositoryAllowed(input.repositoryRoot, input.path);
        const original = await fs.promises.readFile(resolved.target, "utf8").catch(() => null);
        if (original === null && input.operation !== "create") return fail("tool_validation", "File does not exist for modification.", { path: resolved.relative });
        if (original !== null && input.originalSha256 && sha256(original) !== input.originalSha256) {
            return fail("patch_conflict", "Original file hash does not match.", { path: resolved.relative });
        }
        return ok({
            path: resolved.relative,
            operation: original === null ? "create" : "modify",
            original_sha256: original === null ? null : sha256(original),
            modified_sha256: sha256(input.modifiedContent),
            diff: buildUnifiedDiff(resolved.relative, original || "", input.modifiedContent),
            risk: original === null ? "low" : "medium",
            applied: false,
        });
    }
));

register(createTool(
    "validate_patch",
    "Validate a low-risk patch operation before applying it.",
    (input) => {
        if (!input.repositoryRoot || !input.path || !input.operation) throw new Error("repositoryRoot, path and operation are required.");
    },
    async (input) => validatePatchOperation(input)
));

register(createTool(
    "apply_patch",
    "Apply a validated low-risk create, modify, or folder patch with an undo snapshot.",
    (input) => {
        if (!input.repositoryRoot || !input.path || !input.operation) throw new Error("repositoryRoot, path and operation are required.");
    },
    async (input) => {
        const validation = await validatePatchOperation(input);
        if (!validation.ok) return validation;
        const resolved = await assertRepositoryAllowed(input.repositoryRoot, validation.path);
        let originalContent = null;
        if (validation.operation === "modify") {
            originalContent = await fs.promises.readFile(resolved.target, "utf8");
            await fs.promises.writeFile(resolved.target, input.modifiedContent, "utf8");
        } else if (validation.operation === "create") {
            await fs.promises.mkdir(path.dirname(resolved.target), { recursive: true });
            await fs.promises.writeFile(resolved.target, input.modifiedContent, { flag: "wx" });
        } else if (validation.operation === "folder") {
            await fs.promises.mkdir(resolved.target, { recursive: false });
        }
        const rollbackSnapshotId = createRollbackSnapshot(input, validation, originalContent);
        return ok({
            operation: validation.operation,
            path: validation.path,
            applied: true,
            changed_paths: [validation.path],
            rollback_snapshot_id: rollbackSnapshotId,
            original_sha256: validation.original_sha256 || null,
            modified_sha256: validation.modified_sha256 || null,
            review_required: false,
        });
    }
));

register(createTool(
    "rollback_patch",
    "Undo a previously applied low-risk patch snapshot.",
    (input) => {
        if (!input.rollback_snapshot_id) throw new Error("rollback_snapshot_id is required.");
    },
    async (input) => {
        const snapshot = rollbackSnapshots.get(input.rollback_snapshot_id);
        if (!snapshot) return fail("tool_validation", "Rollback snapshot was not found.");
        if (snapshot.used) return fail("tool_validation", "Rollback snapshot has already been used.");
        const resolved = await assertRepositoryAllowed(snapshot.repositoryRoot, snapshot.path);
        if (snapshot.operation === "create") {
            const content = await fs.promises.readFile(resolved.target, "utf8").catch(() => null);
            if (content !== null && snapshot.modified_sha256 && sha256(content) !== snapshot.modified_sha256) {
                return fail("patch_conflict", "Created file changed after apply; rollback requires review.", { path: snapshot.path });
            }
            await fs.promises.rm(resolved.target, { force: true });
        } else if (snapshot.operation === "modify") {
            const content = await fs.promises.readFile(resolved.target, "utf8").catch(() => null);
            if (content !== null && snapshot.modified_sha256 && sha256(content) !== snapshot.modified_sha256) {
                return fail("patch_conflict", "Modified file changed after apply; rollback requires review.", { path: snapshot.path });
            }
            await fs.promises.writeFile(resolved.target, snapshot.original_content || "", "utf8");
        } else if (snapshot.operation === "folder") {
            const entries = await fs.promises.readdir(resolved.target).catch(() => []);
            if (entries.length > 0) return fail("rollback_blocked", "Created folder is no longer empty; rollback requires review.", { path: snapshot.path });
            await fs.promises.rmdir(resolved.target).catch(() => {});
        }
        snapshot.used = true;
        snapshot.used_at = nowIso();
        return ok({
            rollback_snapshot_id: input.rollback_snapshot_id,
            restored: true,
            restored_paths: [snapshot.path],
            operation: snapshot.operation,
        });
    }
));

register(createTool(
    "create_file",
    "Create a new file inside the repository.",
    (input) => {
        if (!input.repositoryRoot || !input.path || typeof input.content !== "string") throw new Error("repositoryRoot, path and content are required.");
    },
    async (input) => {
        const resolved = await assertRepositoryAllowed(input.repositoryRoot, input.path);
        await fs.promises.mkdir(path.dirname(resolved.target), { recursive: true });
        await fs.promises.writeFile(resolved.target, input.content, { flag: "wx" });
        return ok({ path: resolved.relative, created: true, sha256: sha256(input.content) });
    }
));

register(createTool(
    "rename_file",
    "Propose a file rename without applying it.",
    (input) => {
        if (!input.repositoryRoot || !input.from || !input.to) throw new Error("repositoryRoot, from and to are required.");
    },
    async (input) => {
        const from = await assertRepositoryAllowed(input.repositoryRoot, input.from);
        const to = await assertRepositoryAllowed(input.repositoryRoot, input.to);
        return ok({ operation: "rename", from: from.relative, to: to.relative, applied: false, review_required: true });
    }
));

register(createTool(
    "delete_file",
    "Propose a file deletion without applying it.",
    (input) => {
        if (!input.repositoryRoot || !input.path) throw new Error("repositoryRoot and path are required.");
    },
    async (input) => {
        const resolved = await assertRepositoryAllowed(input.repositoryRoot, input.path);
        const stat = await fs.promises.stat(resolved.target);
        return ok({ operation: "delete", path: resolved.relative, size_bytes: stat.size, applied: false, review_required: true });
    }
));

register(createTool(
    "run_command",
    "Run an allowlisted command in the repository.",
    (input) => {
        const validation = validateCommand(input);
        if (!validation.ok) {
            const error = new Error(validation.message);
            error.code = validation.reason;
            throw error;
        }
        if (!input.repositoryRoot) throw new Error("repositoryRoot is required.");
    },
    async (input) => {
        const root = await assertRepositoryRoot(input.repositoryRoot);
        const result = await runCommand({ ...input, cwd: root });
        return ok(result);
    }
));

register(createTool(
    "cancel_command",
    "Cancel a running command by command id.",
    (input) => {
        if (!input.command_id) throw new Error("command_id is required.");
    },
    async (input) => {
        const result = cancelCommand(String(input.command_id));
        return result.ok ? ok(result) : fail("tool_validation", result.message, result);
    }
));

register(createTool(
    "git_status",
    "Run git status --short in the repository.",
    (input) => {
        if (!input.repositoryRoot) throw new Error("repositoryRoot is required.");
    },
    async (input) => {
        const root = await assertRepositoryRoot(input.repositoryRoot);
        const result = await runCommand({ repositoryRoot: root, command: "git", args: ["status", "--short"], cwd: root, timeout_ms: 20_000 });
        return ok(result);
    }
));

async function invokeTool(toolId, input = {}) {
    const tool = tools.get(toolId);
    const startedAt = Date.now();
    if (!tool) {
        const result = fail("tool_validation", `Unknown tool: ${toolId}`);
        return { ...result, audit: auditRecord(toolId, input, result, startedAt) };
    }
    let result;
    try {
        tool.validate(input);
        result = await tool.execute(input);
    } catch (error) {
        result = fail(error.code || "tool_validation", error.message || "Tool failed.");
    }
    const audit = tool.audit(input, result, startedAt);
    return { ...result, audit };
}

function listTools() {
    return [...tools.values()].map((tool) => ({ id: tool.id, description: tool.description }));
}

function getAuditLog() {
    return [...auditLog];
}

module.exports = {
    getAuditLog,
    invokeTool,
    listTools,
};
