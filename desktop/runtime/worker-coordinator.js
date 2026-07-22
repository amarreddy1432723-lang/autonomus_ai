const crypto = require("crypto");

const { ControlledTaskExecutorAdapter } = require("./executors/controlled-task-executor-adapter");
const { ExecutionJournal } = require("./recovery/execution-journal");
const { reconcileRepository, recoveryDecision } = require("./recovery/repository-reconciler");

const DEFAULT_LIMITS = {
    total: 2,
    read_only: 2,
    write_sensitive: 1,
    verification: 1,
    integration: 1,
    review: 1,
};

function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function slotId() {
    return crypto.randomUUID ? crypto.randomUUID() : `slot_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

class WorkerCoordinator {
    constructor({
        apiClient,
        desktopSessionId,
        repositoryRoot,
        repositoryId,
        taskExecutorFactory = () => new ControlledTaskExecutorAdapter(),
        maxWorkers = 2,
        limits = {},
        pollIntervalMs = 5000,
        heartbeatIntervalMs = 20000,
        logger = console,
        executionJournal = new ExecutionJournal({ logger }),
    }) {
        if (!apiClient) throw new Error("apiClient is required.");
        this.apiClient = apiClient;
        this.desktopSessionId = desktopSessionId;
        this.repositoryRoot = repositoryRoot;
        this.repositoryId = repositoryId;
        this.taskExecutorFactory = taskExecutorFactory;
        this.maxWorkers = maxWorkers;
        this.limits = { ...DEFAULT_LIMITS, ...limits, total: maxWorkers };
        this.pollIntervalMs = pollIntervalMs;
        this.heartbeatIntervalMs = heartbeatIntervalMs;
        this.executionJournal = executionJournal;
        this.logger = logger;
        this.slots = new Map();
        this.running = false;
        this.pollTimer = null;
        this.events = [];
        this.applyLock = Promise.resolve();
    }

    emit(event, payload = {}) {
        const record = { event, timestamp: new Date().toISOString(), ...payload };
        this.events.push(record);
        if (this.events.length > 500) this.events.shift();
        return record;
    }

    async start() {
        if (this.running) return;
        this.running = true;
        this.emit("worker.coordinator.started");
        await this.recoverUnfinishedExecutions();
        await this.pollAssignments();
        this.pollTimer = setInterval(() => {
            this.pollAssignments().catch((error) => this.logger.warn?.("worker poll failed", error));
        }, this.pollIntervalMs);
    }

    async recoverUnfinishedExecutions() {
        const entries = await this.executionJournal.listUnfinished();
        for (const entry of entries) {
            try {
                let backendState = "unknown";
                if (this.apiClient.getAssignmentState && entry.mission_id && entry.assignment_id) {
                    const assignment = await this.apiClient.getAssignmentState({
                        missionId: entry.mission_id,
                        assignmentId: entry.assignment_id,
                    });
                    backendState = assignment?.status || "missing";
                }
                const reconciliation = await reconcileRepository({
                    repositoryRoot: entry.repository_root || this.repositoryRoot,
                    files: entry.files || entry.change_set?.changes || [],
                });
                const decision = recoveryDecision({
                    localStage: entry.stage,
                    backendState,
                    repositoryState: reconciliation.repository_state,
                });
                const report = {
                    status: decision.status,
                    local_stage: entry.stage,
                    repository_state: reconciliation.repository_state,
                    recommended_action: decision.recommended_action,
                    artifacts: {
                        change_set_id: entry.change_set_id || null,
                        snapshot_id: entry.snapshot_id || null,
                    },
                    reconciliation: {
                        ...reconciliation,
                        backend_state: backendState,
                        reason: decision.reason,
                    },
                    report_id: `recovery_${entry.assignment_id}_${entry.stage}`,
                };
                if (this.apiClient.reportAssignmentRecovery) {
                    await this.apiClient.reportAssignmentRecovery(entry.assignment_id, report);
                }
                if (["abandoned", "recovered"].includes(decision.status)) {
                    await this.executionJournal.remove(entry.assignment_id);
                } else {
                    await this.executionJournal.update(entry.assignment_id, {
                        recovery_status: decision.status,
                        recommended_action: decision.recommended_action,
                        repository_state: reconciliation.repository_state,
                        backend_state: backendState,
                    });
                }
                this.emit("assignment.recovery.reconciled", {
                    assignmentId: entry.assignment_id,
                    stage: entry.stage,
                    backendState,
                    repositoryState: reconciliation.repository_state,
                    recommendedAction: decision.recommended_action,
                });
            } catch (error) {
                this.emit("assignment.recovery.failed", { assignmentId: entry.assignment_id, message: error.message });
                this.logger.warn?.("assignment recovery failed", error);
            }
        }
    }

    async stop() {
        this.running = false;
        if (this.pollTimer) clearInterval(this.pollTimer);
        this.pollTimer = null;
        for (const slot of this.slots.values()) {
            slot.status = "stopping";
            slot.abortController?.abort();
        }
        await Promise.allSettled([...this.slots.values()].map((slot) => slot.currentRun).filter(Boolean));
        this.emit("worker.coordinator.stopped");
    }

    activeSlots() {
        return [...this.slots.values()].filter((slot) => !["idle", "failed", "stopping"].includes(slot.status));
    }

    classCount(executionClass) {
        return this.activeSlots().filter((slot) => slot.executionClass === executionClass).length;
    }

    hasCapacity(assignment) {
        const active = this.activeSlots();
        if (active.length >= this.limits.total) return false;
        if (active.some((slot) => slot.assignmentId === assignment.assignment_id || slot.taskId === assignment.task_id)) return false;
        const executionClass = assignment.execution_class || "read_only";
        if (this.classCount(executionClass) >= (this.limits[executionClass] ?? this.limits.total)) return false;
        return true;
    }

    createSlot(assignment) {
        const slot = {
            slotId: slotId(),
            status: "idle",
            assignmentId: assignment.assignment_id,
            missionId: assignment.mission_id,
            taskId: assignment.task_id,
            workerId: assignment.worker_id,
            executionClass: assignment.execution_class || "read_only",
            startedAt: null,
            lastHeartbeatAt: null,
            abortController: new AbortController(),
            evidence: [],
            changeSet: null,
        };
        this.slots.set(slot.slotId, slot);
        this.emit("worker.slot.created", { slotId: slot.slotId, assignmentId: slot.assignmentId, taskId: slot.taskId });
        return slot;
    }

    async pollAssignments() {
        if (!this.running && this.pollTimer) return;
        const available = await this.apiClient.availableAssignments({
            desktopSessionId: this.desktopSessionId,
            repositoryId: this.repositoryId,
            limit: this.maxWorkers * 2,
        });
        for (const assignment of available.assignments || []) {
            if (!this.hasCapacity(assignment)) continue;
            const slot = this.createSlot(assignment);
            slot.currentRun = this.runAssignment(slot, assignment);
        }
    }

    async runAssignment(slot, assignment) {
        let taskLease = null;
        try {
            slot.status = "accepting";
            this.emit("assignment.discovered", { assignmentId: assignment.assignment_id, taskId: assignment.task_id });
            await this.executionJournal.write({
                assignment_id: assignment.assignment_id,
                mission_id: assignment.mission_id,
                task_id: assignment.task_id,
                worker_id: assignment.worker_id,
                repository_root: this.repositoryRoot,
                stage: "accepted",
                execution_class: assignment.execution_class || "read_only",
                assignment,
            });
            await this.apiClient.acceptAssignment(assignment.assignment_id, { workerId: assignment.worker_id });
            this.emit("assignment.accepted", { assignmentId: assignment.assignment_id });

            taskLease = await this.apiClient.claimTask({
                missionId: assignment.mission_id,
                taskId: assignment.task_id,
                desktopSessionId: this.desktopSessionId,
                expectedTaskVersion: assignment.task_version,
                ttlSeconds: 90,
            });
            await this.executionJournal.update(assignment.assignment_id, {
                stage: "claimed",
                task_lease_token: taskLease.lease_token,
                task_lease_id: taskLease.lease_id,
            });
            slot.taskLeaseToken = taskLease.lease_token;
            slot.status = "running";
            slot.startedAt = new Date().toISOString();
            slot.heartbeatStopped = false;
            await this.executionJournal.update(assignment.assignment_id, { stage: "context_hydrated" });
            this.emit("assignment.execution.started", { assignmentId: assignment.assignment_id, slotId: slot.slotId });

            const heartbeatLoop = this.renewLeases(slot).finally(() => {});
            const executor = this.taskExecutorFactory(assignment);
            const result = await executor.execute(
                {
                    assignment,
                    repositoryRoot: this.repositoryRoot,
                    targetPath: assignment.metadata?.target_path,
                    taskLease,
                },
                {
                    onStageChanged: async (stage) => {
                        slot.stage = stage;
                        await this.executionJournal.update(assignment.assignment_id, { stage });
                        this.emit("worker.slot.stage", { slotId: slot.slotId, stage });
                    },
                    onProgress: async (progress) => {
                        slot.progress = progress;
                    },
                    onEvidence: async (record) => {
                        slot.evidence.push(record);
                    },
                    onChangeSet: async (changeSet) => {
                        slot.changeSet = changeSet;
                        await this.executionJournal.update(assignment.assignment_id, {
                            stage: changeSet?.review_state === "rolled_back" ? "rolled_back" : "patch_staged",
                            change_set: changeSet,
                            files: changeSet?.changes || [],
                        });
                    },
                    onWarning: async (warning) => {
                        this.emit("worker.slot.warning", { slotId: slot.slotId, warning });
                    },
                }
            );
            slot.heartbeatStopped = true;
            await heartbeatLoop;

            const evidenceResponse = await this.apiClient.postToolEvidence({
                missionId: assignment.mission_id,
                taskId: assignment.task_id,
                records: slot.evidence,
                summary: `Worker slot ${slot.slotId} emitted ${slot.evidence.length} evidence record(s).`,
            });
            const changeSetResponse = await this.apiClient.postChangeSet({
                missionId: assignment.mission_id,
                taskId: assignment.task_id,
                changeSet: slot.changeSet,
            });
            await this.executionJournal.update(assignment.assignment_id, {
                stage: "verifying",
                change_set_id: changeSetResponse?.id || null,
            });
            await this.apiClient.completeTask({
                missionId: assignment.mission_id,
                taskId: assignment.task_id,
                leaseToken: taskLease.lease_token,
                result: {
                    status: result.status || "completed",
                    summary: "Assignment executed by desktop worker coordinator.",
                    evidence_count: slot.evidence.length,
                    payload: { context: result.context || {}, slot_id: slot.slotId },
                },
            });
            await this.apiClient.completeAssignment(assignment.assignment_id, {
                worker_id: assignment.worker_id,
                task_status: "completed",
                task_result_id: taskLease.lease_id || null,
                evidence_count: slot.evidence.length,
                change_set_id: changeSetResponse?.id || null,
                result: { evidence_id: evidenceResponse?.id || null },
            });
            slot.status = "idle";
            await this.executionJournal.update(assignment.assignment_id, { stage: "completed" });
            await this.executionJournal.remove(assignment.assignment_id);
            this.emit("assignment.completed", { assignmentId: assignment.assignment_id, slotId: slot.slotId });
        } catch (error) {
            slot.heartbeatStopped = true;
            slot.status = "failed";
            this.emit("assignment.failed", { assignmentId: assignment.assignment_id, message: error.message });
            try {
                await this.apiClient.failAssignment(assignment.assignment_id, {
                    worker_id: assignment.worker_id,
                    error: {
                        code: error.code || "EXECUTOR_FAILED",
                        category: "desktop_worker",
                        message: error.message || "Worker execution failed.",
                        retryable: false,
                    },
                });
            } catch (failError) {
                this.logger.warn?.("assignment failure report failed", failError);
            }
        } finally {
            slot.heartbeatStopped = true;
            slot.abortController = null;
            if (slot.status !== "failed") slot.status = "idle";
            this.emit("worker.slot.idle", { slotId: slot.slotId, assignmentId: slot.assignmentId });
        }
    }

    async renewLeases(slot) {
        while (!slot.heartbeatStopped && slot.status === "running") {
            let waited = 0;
            while (!slot.heartbeatStopped && slot.status === "running" && waited < this.heartbeatIntervalMs) {
                const step = Math.min(250, this.heartbeatIntervalMs - waited);
                await delay(step);
                waited += step;
            }
            if (slot.heartbeatStopped || slot.status !== "running") break;
            try {
                await Promise.all([
                    this.apiClient.heartbeatAssignment(slot.assignmentId, { workerId: slot.workerId }),
                    slot.taskLeaseToken
                        ? this.apiClient.renewTaskLease({
                              missionId: slot.missionId,
                              taskId: slot.taskId,
                              leaseToken: slot.taskLeaseToken,
                              ttlSeconds: 90,
                          })
                        : Promise.resolve(null),
                ]);
                slot.lastHeartbeatAt = new Date().toISOString();
                this.emit("assignment.heartbeat", { assignmentId: slot.assignmentId, slotId: slot.slotId });
            } catch (error) {
                this.emit("assignment.heartbeat.failed", { assignmentId: slot.assignmentId, slotId: slot.slotId, message: error.message });
            }
        }
    }

    snapshot() {
        return {
            running: this.running,
            slots: [...this.slots.values()].map((slot) => ({
                slotId: slot.slotId,
                status: slot.status,
                assignmentId: slot.assignmentId,
                missionId: slot.missionId,
                taskId: slot.taskId,
                workerId: slot.workerId,
                executionClass: slot.executionClass,
                startedAt: slot.startedAt,
                lastHeartbeatAt: slot.lastHeartbeatAt,
                evidenceCount: slot.evidence.length,
            })),
            events: [...this.events],
        };
    }
}

module.exports = {
    WorkerCoordinator,
};
