const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

function sha256Bytes(value) {
    return crypto.createHash("sha256").update(value).digest("hex");
}

async function fileHash(absolutePath) {
    try {
        const data = await fs.promises.readFile(absolutePath);
        return sha256Bytes(data);
    } catch (error) {
        if (error.code === "ENOENT") return null;
        throw error;
    }
}

function normalizePath(relativePath) {
    return String(relativePath || "").replace(/\\/g, "/").replace(/^\/+/, "");
}

function expectedHashFor(file) {
    return file.expected_sha256 || file.modified_sha256 || file.applied_sha256 || null;
}

function snapshotHashFor(file) {
    return file.snapshot_sha256 || file.original_sha256 || null;
}

function classifyFile({ file, currentSha256 }) {
    const originalSha256 = file.original_sha256 ?? null;
    const expectedSha256 = expectedHashFor(file);
    const snapshotSha256 = snapshotHashFor(file);
    const operation = file.operation || "modify";

    if (currentSha256 === null) {
        if (operation === "delete" && expectedSha256 === null) return "expected_modified";
        return "missing";
    }
    if (expectedSha256 && currentSha256 === expectedSha256) return "expected_modified";
    if (originalSha256 && currentSha256 === originalSha256) return "unchanged";
    if (snapshotSha256 && currentSha256 === snapshotSha256) return "unchanged";
    if (!originalSha256 && operation === "create") return "unexpectedly_created";
    if (expectedSha256) return "partially_modified";
    return "externally_modified";
}

function summarizeClassifications(classifications) {
    if (classifications.length === 0) return "unchanged";
    const states = new Set(classifications.map((item) => item.state));
    if (states.has("partially_modified") || states.has("externally_modified")) return "conflicted";
    if (states.has("missing")) return "missing";
    if (states.has("unexpectedly_created")) return "unexpectedly_created";
    if (states.size === 1 && states.has("expected_modified")) return "expected_modified";
    if (states.size === 1 && states.has("unchanged")) return "unchanged";
    if (states.has("expected_modified") && states.has("unchanged")) return "partially_modified";
    return "conflicted";
}

async function reconcileRepository({ repositoryRoot, files = [] }) {
    if (!repositoryRoot) throw new Error("repositoryRoot is required.");
    const root = path.resolve(repositoryRoot);
    const classifications = [];
    for (const file of files) {
        const relativePath = normalizePath(file.path || file.filename);
        if (!relativePath) continue;
        const absolutePath = path.resolve(root, relativePath);
        if (!absolutePath.startsWith(root)) {
            classifications.push({
                path: relativePath,
                state: "externally_modified",
                reason: "Path resolves outside repository root.",
            });
            continue;
        }
        const currentSha256 = await fileHash(absolutePath);
        classifications.push({
            path: relativePath,
            operation: file.operation || "modify",
            state: classifyFile({ file, currentSha256 }),
            current_sha256: currentSha256,
            original_sha256: file.original_sha256 ?? null,
            expected_sha256: expectedHashFor(file),
            snapshot_sha256: snapshotHashFor(file),
        });
    }
    const repositoryState = summarizeClassifications(classifications);
    return {
        repository_state: repositoryState,
        files: classifications,
    };
}

function recoveryDecision({ localStage, backendState, repositoryState }) {
    if (["partial", "partially_modified", "conflicted", "externally_modified", "missing"].includes(repositoryState)) {
        return {
            status: "manual_review_required",
            recommended_action: "manual_review",
            reason: "Repository state does not match a deterministic original or expected hash.",
        };
    }
    if (localStage === "patch_staged" && backendState === "expired") {
        return {
            status: "reconciled",
            recommended_action: "preserve_patch_for_review",
            reason: "Patch was staged but not applied.",
        };
    }
    if (localStage === "applied" && backendState === "expired" && repositoryState === "expected_modified") {
        return {
            status: "reconciled",
            recommended_action: "verify_and_complete",
            reason: "Repository matches expected patched hashes.",
        };
    }
    if (localStage === "rolled_back" && backendState === "expired" && repositoryState === "unchanged") {
        return {
            status: "recovered",
            recommended_action: "close_recovery",
            reason: "Rollback restored original hashes.",
        };
    }
    if (localStage === "executing" && backendState === "expired") {
        return {
            status: "abandoned",
            recommended_action: "cleanup_temporary_files",
            reason: "No durable local patch or snapshot stage was reached.",
        };
    }
    return {
        status: "reconciled",
        recommended_action: "rerun_verification",
        reason: "State is deterministic but requires a verification pass before completion.",
    };
}

module.exports = {
    reconcileRepository,
    recoveryDecision,
    sha256Bytes,
};
