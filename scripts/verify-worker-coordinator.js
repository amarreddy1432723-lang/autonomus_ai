const assert = require("assert");
const { WorkerCoordinator } = require("../desktop/runtime/worker-coordinator");

function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

class FakeApiClient {
    constructor(assignments) {
        this.assignments = assignments.map((assignment) => ({ ...assignment, status: "assigned" }));
        this.accepted = [];
        this.claimed = [];
        this.completed = [];
        this.heartbeats = [];
    }

    async availableAssignments({ limit }) {
        return { assignments: this.assignments.filter((assignment) => assignment.status === "assigned").slice(0, limit) };
    }

    async acceptAssignment(assignmentId, { workerId }) {
        const assignment = this.assignments.find((item) => item.assignment_id === assignmentId);
        assert(assignment, "assignment exists");
        assert.strictEqual(assignment.worker_id, workerId);
        assignment.status = "accepted";
        this.accepted.push({ assignmentId, at: Date.now() });
        return { id: assignmentId, status: "accepted" };
    }

    async claimTask({ missionId, taskId }) {
        this.claimed.push({ missionId, taskId, at: Date.now() });
        return { lease_id: `lease-${taskId}`, lease_token: `token-${taskId}` };
    }

    async heartbeatAssignment(assignmentId) {
        this.heartbeats.push({ assignmentId, at: Date.now() });
        return { id: assignmentId, status: "accepted" };
    }

    async renewTaskLease() {
        return { status: "claimed" };
    }

    async postToolEvidence() {
        return { id: "evidence" };
    }

    async postChangeSet() {
        return null;
    }

    async completeTask({ taskId }) {
        return { task_id: taskId, task_status: "completed" };
    }

    async completeAssignment(assignmentId) {
        const assignment = this.assignments.find((item) => item.assignment_id === assignmentId);
        assignment.status = "completed";
        this.completed.push({ assignmentId, at: Date.now() });
        return { id: assignmentId, status: "completed" };
    }

    async failAssignment(assignmentId, payload) {
        const assignment = this.assignments.find((item) => item.assignment_id === assignmentId);
        assignment.status = "failed";
        return { id: assignmentId, status: "failed", payload };
    }
}

class TimedExecutor {
    constructor(timeline, durationMs) {
        this.timeline = timeline;
        this.durationMs = durationMs;
    }

    async execute(context, hooks) {
        const started = Date.now();
        this.timeline.push({ taskId: context.assignment.task_id, type: "start", at: started });
        await hooks.onEvidence?.({
            tool: "fake_executor",
            input_summary: context.assignment.task_id,
            output_summary: "completed",
            status: "succeeded",
            duration_ms: this.durationMs,
            payload: {},
        });
        await delay(this.durationMs);
        const finished = Date.now();
        this.timeline.push({ taskId: context.assignment.task_id, type: "finish", at: finished });
        return { status: "completed", context: { duration_ms: this.durationMs } };
    }
}

async function main() {
    const assignments = [
        {
            assignment_id: "assignment-a",
            mission_id: "mission",
            task_id: "task-a",
            task_key: "read_a",
            task_type: "analysis",
            task_version: 1,
            worker_id: "worker-a",
            execution_class: "read_only",
            metadata: {},
        },
        {
            assignment_id: "assignment-b",
            mission_id: "mission",
            task_id: "task-b",
            task_key: "write_b",
            task_type: "implementation",
            task_version: 1,
            worker_id: "worker-b",
            execution_class: "write_sensitive",
            metadata: {},
        },
        {
            assignment_id: "assignment-c",
            mission_id: "mission",
            task_id: "task-c",
            task_key: "read_c",
            task_type: "analysis",
            task_version: 1,
            worker_id: "worker-c",
            execution_class: "read_only",
            metadata: {},
        },
    ];
    const timeline = [];
    const apiClient = new FakeApiClient(assignments);
    const coordinator = new WorkerCoordinator({
        apiClient,
        desktopSessionId: "desktop-session",
        repositoryRoot: process.cwd(),
        maxWorkers: 2,
        pollIntervalMs: 10_000,
        heartbeatIntervalMs: 25,
        taskExecutorFactory: () => new TimedExecutor(timeline, 120),
        logger: { warn() {} },
    });

    await coordinator.start();
    while (apiClient.completed.length < 2) {
        await delay(20);
    }
    await coordinator.stop();

    const starts = timeline.filter((item) => item.type === "start");
    const finishes = timeline.filter((item) => item.type === "finish");
    const firstFinish = Math.min(...finishes.map((item) => item.at));
    const secondStart = starts.sort((a, b) => a.at - b.at)[1].at;
    const overlap = secondStart < firstFinish;
    const snapshot = coordinator.snapshot();
    const result = {
        ok:
            apiClient.accepted.length === 2 &&
            apiClient.claimed.length === 2 &&
            apiClient.completed.length === 2 &&
            apiClient.heartbeats.length >= 2 &&
            overlap &&
            snapshot.slots.length === 2,
        accepted: apiClient.accepted.length,
        claimed: apiClient.claimed.length,
        completed: apiClient.completed.length,
        heartbeats: apiClient.heartbeats.length,
        overlap,
        slots: snapshot.slots.length,
    };
    console.log(JSON.stringify(result));
    if (!result.ok) process.exit(1);
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
