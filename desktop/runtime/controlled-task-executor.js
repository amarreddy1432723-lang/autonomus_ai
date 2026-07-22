const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const { invokeTool } = require("./tool-registry");

function sha256(value) {
    return crypto.createHash("sha256").update(String(value)).digest("hex");
}

function evidenceFrom(result, fallbackTool) {
    const audit = result.audit || {};
    return {
        tool: audit.tool || fallbackTool,
        input_summary: audit.input_summary || "",
        output_summary: audit.output_summary || "",
        duration_ms: audit.duration_ms || 0,
        status: result.ok ? "succeeded" : "failed",
        error_class: result.error_class || null,
        audit_id: audit.id || null,
        timestamp: audit.timestamp || new Date().toISOString(),
        payload: {
            path: result.path || null,
            operation: result.operation || null,
            changed_paths: result.changed_paths || [],
            restored_paths: result.restored_paths || [],
        },
    };
}

function assertOk(label, result) {
    if (!result.ok) {
        const error = new Error(`${label} failed: ${result.message || result.error_class || "unknown error"}`);
        error.result = result;
        throw error;
    }
}

async function executeProjectSummaryTask(repositoryRoot, options = {}) {
    const targetPath = options.path || "PROJECT_SUMMARY.md";
    const summaryContent = options.content || [
        "# Project Summary",
        "",
        "This fixture repository contains a small FastAPI backend, a Next.js frontend, and a smoke test.",
        "Arceus generated this summary through the controlled desktop task executor.",
        "",
    ].join("\n");
    const steps = [];
    const evidence = [];

    async function run(tool, input) {
        const result = await invokeTool(tool, input);
        steps.push({ tool, ok: result.ok, message: result.message || null });
        evidence.push(evidenceFrom(result, tool));
        assertOk(tool, result);
        return result;
    }

    const targetAbsolute = path.join(repositoryRoot, targetPath);
    await fs.promises.rm(targetAbsolute, { force: true });

    const directory = await run("read_directory", { repositoryRoot, path: "." });
    const packageJson = await run("read_file", { repositoryRoot, path: "package.json" });
    const requirements = await run("read_file", { repositoryRoot, path: "requirements.txt" });
    const authService = await run("read_file", { repositoryRoot, path: "backend/services/auth/main.py" });
    const search = await run("search_repository", { repositoryRoot, query: "FastAPI" });
    const symbol = await run("inspect_symbol", { repositoryRoot, symbol: "login" });
    const patch = await run("propose_patch", {
        repositoryRoot,
        path: targetPath,
        operation: "create",
        modifiedContent: summaryContent,
    });
    const validation = await run("validate_patch", {
        repositoryRoot,
        path: targetPath,
        operation: "create",
        modifiedContent: summaryContent,
    });
    const apply = await run("apply_patch", {
        repositoryRoot,
        path: targetPath,
        operation: "create",
        modifiedContent: summaryContent,
    });

    const appliedContent = await fs.promises.readFile(targetAbsolute, "utf8");
    const applyVerified = appliedContent === summaryContent;
    steps.push({ tool: "verify_file_exists", ok: applyVerified, message: applyVerified ? null : "Applied file content did not match expected content." });
    evidence.push({
        tool: "verify_file_exists",
        input_summary: targetPath,
        output_summary: applyVerified ? "Verified applied file exists with expected content." : "Applied file verification failed.",
        duration_ms: 0,
        status: applyVerified ? "succeeded" : "failed",
        error_class: applyVerified ? null : "verification_failed",
        audit_id: `verify_${Date.now()}`,
        timestamp: new Date().toISOString(),
        payload: { path: targetPath, sha256: sha256(appliedContent) },
    });
    if (!applyVerified) {
        throw new Error("Applied file verification failed.");
    }

    const rollback = await run("rollback_patch", {
        rollback_snapshot_id: apply.rollback_snapshot_id,
    });
    const rolledBack = !fs.existsSync(targetAbsolute);
    steps.push({ tool: "verify_rollback", ok: rolledBack, message: rolledBack ? null : "Rollback did not remove created file." });
    evidence.push({
        tool: "verify_rollback",
        input_summary: targetPath,
        output_summary: rolledBack ? "Verified rollback restored repository to pre-change state." : "Rollback verification failed.",
        duration_ms: 0,
        status: rolledBack ? "succeeded" : "failed",
        error_class: rolledBack ? null : "rollback_failed",
        audit_id: `rollback_verify_${Date.now()}`,
        timestamp: new Date().toISOString(),
        payload: { path: targetPath, restored: rolledBack },
    });
    if (!rolledBack) {
        throw new Error("Rollback verification failed.");
    }

    return {
        status: "completed",
        repository_root: repositoryRoot,
        target_path: targetPath,
        steps,
        evidence,
        context: {
            root_entries: directory.entries?.length || 0,
            package_sha256: packageJson.sha256,
            requirements_sha256: requirements.sha256,
            auth_service_sha256: authService.sha256,
            search_matches: search.matches?.length || 0,
            symbol_matches: symbol.matches?.length || 0,
        },
        change_set: {
            title: "Controlled desktop task patch",
            summary: "Desktop worker created, applied, verified, and rolled back PROJECT_SUMMARY.md.",
            review_state: "rolled_back",
            source: "desktop_tool_runtime",
            changes: [
                {
                    operation: "create",
                    path: targetPath,
                    old_path: null,
                    diff: patch.diff || validation.diff || "",
                    original_sha256: null,
                    modified_sha256: apply.modified_sha256 || sha256(summaryContent),
                    risk: validation.risk || "low",
                    review_required: false,
                    applied: false,
                    rollback_snapshot_id: apply.rollback_snapshot_id,
                    metadata: {
                        lifecycle: ["proposed", "validated", "applied", "verified", "rolled_back"],
                        restored_paths: rollback.restored_paths || [],
                    },
                },
            ],
            metadata: {
                target_path: targetPath,
                applied_sha256: sha256(summaryContent),
                rollback_verified: true,
            },
        },
    };
}

module.exports = {
    executeProjectSummaryTask,
};
