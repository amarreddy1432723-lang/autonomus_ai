const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const { WorkerCoordinator } = require("../desktop/runtime/worker-coordinator");
const { ExecutionJournal } = require("../desktop/runtime/recovery/execution-journal");
const { reconcileRepository, recoveryDecision, sha256Bytes } = require("../desktop/runtime/recovery/repository-reconciler");

async function tempDir() {
    return fs.promises.mkdtemp(path.join(os.tmpdir(), "arceus-recovery-"));
}

async function writeFile(root, relativePath, content) {
    const absolute = path.join(root, relativePath);
    await fs.promises.mkdir(path.dirname(absolute), { recursive: true });
    await fs.promises.writeFile(absolute, content, "utf8");
    return sha256Bytes(Buffer.from(content, "utf8"));
}

async function exists(filePath) {
    return fs.promises
        .access(filePath)
        .then(() => true)
        .catch(() => false);
}

class FakeRecoveryApi {
    constructor(states = {}) {
        this.states = states;
        this.reports = [];
        this.reportHashes = new Map();
    }

    async availableAssignments() {
        return { assignments: [] };
    }

    async getAssignmentState({ assignmentId }) {
        return { id: assignmentId, status: this.states[assignmentId] || "expired" };
    }

    async reportAssignmentRecovery(assignmentId, payload) {
        const key = payload.report_id || `${assignmentId}:${payload.local_stage}`;
        const hash = JSON.stringify(payload);
        const idempotent = this.reportHashes.get(key) === hash;
        this.reportHashes.set(key, hash);
        this.reports.push({ assignmentId, payload, idempotent });
        return { assignment_id: assignmentId, report_id: key, idempotent };
    }
}

function check(name, ok, detail) {
    return { name, ok: Boolean(ok), detail };
}

async function main() {
    const checks = [];
    const root = await tempDir();
    const journalDir = path.join(root, ".arceus", "journal");
    const journal = new ExecutionJournal({ journalDir, logger: { warn() {} } });

    const originalHash = await writeFile(root, "src/service.txt", "original\n");
    const expectedHash = sha256Bytes(Buffer.from("patched\n", "utf8"));

    await journal.write({
        assignment_id: "assignment-staged",
        mission_id: "mission",
        task_id: "task-staged",
        repository_root: root,
        stage: "patch_staged",
        files: [{ operation: "modify", path: "src/service.txt", original_sha256: originalHash, modified_sha256: expectedHash }],
    });

    await writeFile(root, "src/applied.txt", "patched\n");
    await journal.write({
        assignment_id: "assignment-applied",
        mission_id: "mission",
        task_id: "task-applied",
        repository_root: root,
        stage: "applied",
        change_set_id: "change-applied",
        files: [{ operation: "create", path: "src/applied.txt", original_sha256: null, modified_sha256: expectedHash }],
    });

    const conflictOriginalHash = await writeFile(root, "src/conflict.txt", "original\n");
    const conflictExpectedHash = sha256Bytes(Buffer.from("expected\n", "utf8"));
    await writeFile(root, "src/conflict.txt", "external\n");
    await journal.write({
        assignment_id: "assignment-conflict",
        mission_id: "mission",
        task_id: "task-conflict",
        repository_root: root,
        stage: "snapshot_created",
        snapshot_id: "snapshot-conflict",
        files: [{ operation: "modify", path: "src/conflict.txt", original_sha256: conflictOriginalHash, modified_sha256: conflictExpectedHash }],
    });

    const rollbackOriginalHash = await writeFile(root, "src/rollback.txt", "original\n");
    await journal.write({
        assignment_id: "assignment-rollback",
        mission_id: "mission",
        task_id: "task-rollback",
        repository_root: root,
        stage: "rolled_back",
        snapshot_id: "snapshot-rollback",
        files: [{ operation: "modify", path: "src/rollback.txt", original_sha256: rollbackOriginalHash, modified_sha256: sha256Bytes(Buffer.from("patched\n", "utf8")) }],
    });

    const stagedRecon = await reconcileRepository({
        repositoryRoot: root,
        files: [{ operation: "modify", path: "src/service.txt", original_sha256: originalHash, modified_sha256: expectedHash }],
    });
    const stagedDecision = recoveryDecision({ localStage: "patch_staged", backendState: "expired", repositoryState: stagedRecon.repository_state });
    checks.push(check("Staged patch leaves repository unchanged", stagedRecon.repository_state === "unchanged", stagedRecon.repository_state));
    checks.push(check("Staged patch preserved for review", stagedDecision.recommended_action === "preserve_patch_for_review", stagedDecision.recommended_action));

    const appliedRecon = await reconcileRepository({
        repositoryRoot: root,
        files: [{ operation: "create", path: "src/applied.txt", original_sha256: null, modified_sha256: expectedHash }],
    });
    const appliedDecision = recoveryDecision({ localStage: "applied", backendState: "expired", repositoryState: appliedRecon.repository_state });
    checks.push(check("Applied file matches expected hash", appliedRecon.repository_state === "expected_modified", appliedRecon.repository_state));
    checks.push(check("Applied work recommends verify and complete", appliedDecision.recommended_action === "verify_and_complete", appliedDecision.recommended_action));

    const conflictRecon = await reconcileRepository({
        repositoryRoot: root,
        files: [{ operation: "modify", path: "src/conflict.txt", original_sha256: conflictOriginalHash, modified_sha256: conflictExpectedHash }],
    });
    const conflictDecision = recoveryDecision({ localStage: "snapshot_created", backendState: "expired", repositoryState: conflictRecon.repository_state });
    checks.push(check("External modification detected", conflictRecon.repository_state === "conflicted", conflictRecon.repository_state));
    checks.push(check("Conflict requires manual review", conflictDecision.status === "manual_review_required", conflictDecision.status));

    const rollbackRecon = await reconcileRepository({
        repositoryRoot: root,
        files: [{ operation: "modify", path: "src/rollback.txt", original_sha256: rollbackOriginalHash, modified_sha256: sha256Bytes(Buffer.from("patched\n", "utf8")) }],
    });
    const rollbackDecision = recoveryDecision({ localStage: "rolled_back", backendState: "expired", repositoryState: rollbackRecon.repository_state });
    checks.push(check("Rollback state restored original hash", rollbackRecon.repository_state === "unchanged", rollbackRecon.repository_state));
    checks.push(check("Rollback recovery can close", rollbackDecision.status === "recovered", rollbackDecision.status));

    const api = new FakeRecoveryApi({
        "assignment-staged": "expired",
        "assignment-applied": "expired",
        "assignment-conflict": "expired",
        "assignment-rollback": "expired",
    });
    const coordinator = new WorkerCoordinator({
        apiClient: api,
        desktopSessionId: "desktop",
        repositoryRoot: root,
        executionJournal: journal,
        pollIntervalMs: 60_000,
        logger: { warn() {} },
    });
    await coordinator.recoverUnfinishedExecutions();
    await coordinator.recoverUnfinishedExecutions();
    const unfinished = await journal.listUnfinished();
    const stagedStillExists = Boolean(unfinished.find((entry) => entry.assignment_id === "assignment-staged"));
    const conflictStillExists = Boolean(unfinished.find((entry) => entry.assignment_id === "assignment-conflict"));
    const rollbackRemoved = !(await exists(path.join(journalDir, "assignment-rollback.json")));

    checks.push(check("Coordinator reports recovery to backend", api.reports.length >= 4, `reports=${api.reports.length}`));
    checks.push(check("Recovery report is idempotent", api.reports.some((item) => item.idempotent), `idempotent=${api.reports.filter((item) => item.idempotent).length}`));
    checks.push(check("Staged journal retained until review", stagedStillExists, `unfinished=${unfinished.map((entry) => entry.assignment_id).join(",")}`));
    checks.push(check("Conflict journal retained until review", conflictStillExists, `unfinished=${unfinished.map((entry) => entry.assignment_id).join(",")}`));
    checks.push(check("Recovered rollback journal removed", rollbackRemoved, `rollbackRemoved=${rollbackRemoved}`));

    const result = {
        ok: checks.every((item) => item.ok),
        checks,
    };
    console.log(JSON.stringify(result));
    assert(result.ok, JSON.stringify(checks.filter((item) => !item.ok), null, 2));
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
