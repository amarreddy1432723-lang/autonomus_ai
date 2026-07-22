class AssignmentClient {
    constructor({ baseUrl, headers = {}, fetchImpl = fetch }) {
        if (!baseUrl) throw new Error("baseUrl is required.");
        this.baseUrl = String(baseUrl).replace(/\/$/, "");
        this.headers = { ...headers };
        this.fetchImpl = fetchImpl;
    }

    async request(path, options = {}) {
        const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
            ...options,
            headers: {
                "content-type": "application/json",
                ...this.headers,
                ...(options.headers || {}),
            },
        });
        const text = await response.text();
        const body = text ? JSON.parse(text) : {};
        if (!response.ok) {
            const error = new Error(body?.detail?.error?.message || body?.message || `Request failed with ${response.status}`);
            error.status = response.status;
            error.body = body;
            throw error;
        }
        return body;
    }

    availableAssignments({ desktopSessionId, repositoryId, limit = 10 } = {}) {
        const params = new URLSearchParams();
        if (desktopSessionId) params.set("desktop_session_id", desktopSessionId);
        if (repositoryId) params.set("repository_id", repositoryId);
        params.set("limit", String(limit));
        return this.request(`/api/v1/task-runtime/assignments/available?${params.toString()}`);
    }

    async getAssignmentState({ missionId, assignmentId }) {
        const assignments = await this.request(`/api/v1/task-runtime/missions/${missionId}/assignments`);
        return (assignments || []).find((assignment) => assignment.id === assignmentId) || null;
    }

    acceptAssignment(assignmentId, { workerId, expectedAssignmentVersion } = {}) {
        return this.request(`/api/v1/task-runtime/assignments/${assignmentId}/accept`, {
            method: "POST",
            body: JSON.stringify({ worker_id: workerId, expected_assignment_version: expectedAssignmentVersion ?? null }),
        });
    }

    heartbeatAssignment(assignmentId, { workerId } = {}) {
        return this.request(`/api/v1/task-runtime/assignments/${assignmentId}/heartbeat`, {
            method: "POST",
            body: JSON.stringify({ worker_id: workerId }),
        });
    }

    completeAssignment(assignmentId, payload) {
        return this.request(`/api/v1/task-runtime/assignments/${assignmentId}/complete`, {
            method: "POST",
            body: JSON.stringify(payload),
        });
    }

    failAssignment(assignmentId, payload) {
        return this.request(`/api/v1/task-runtime/assignments/${assignmentId}/fail`, {
            method: "POST",
            body: JSON.stringify(payload),
        });
    }

    reportAssignmentRecovery(assignmentId, payload) {
        return this.request(`/api/v1/task-runtime/assignments/${assignmentId}/recovery`, {
            method: "POST",
            body: JSON.stringify(payload),
        });
    }

    claimTask({ missionId, taskId, desktopSessionId, expectedTaskVersion, ttlSeconds = 90 }) {
        return this.request(`/api/v1/missions/${missionId}/tasks/${taskId}/claim`, {
            method: "POST",
            body: JSON.stringify({
                desktop_session_id: desktopSessionId,
                expected_task_version: expectedTaskVersion,
                ttl_seconds: ttlSeconds,
            }),
        });
    }

    renewTaskLease({ missionId, taskId, leaseToken, ttlSeconds = 90 }) {
        return this.request(`/api/v1/missions/${missionId}/tasks/${taskId}/renew-lease`, {
            method: "POST",
            body: JSON.stringify({ lease_token: leaseToken, ttl_seconds: ttlSeconds }),
        });
    }

    completeTask({ missionId, taskId, leaseToken, result }) {
        return this.request(`/api/v1/missions/${missionId}/tasks/${taskId}/complete`, {
            method: "POST",
            body: JSON.stringify({ lease_token: leaseToken, result }),
        });
    }

    postToolEvidence({ missionId, taskId, records, summary, source = "desktop_worker_coordinator" }) {
        if (!records || records.length === 0) return Promise.resolve(null);
        return this.request(`/api/v1/missions/${missionId}/tasks/${taskId}/tool-evidence`, {
            method: "POST",
            body: JSON.stringify({ records, summary, source }),
        });
    }

    postChangeSet({ missionId, taskId, changeSet }) {
        if (!changeSet) return Promise.resolve(null);
        return this.request(`/api/v1/missions/${missionId}/tasks/${taskId}/change-set`, {
            method: "POST",
            body: JSON.stringify(changeSet),
        });
    }
}

module.exports = {
    AssignmentClient,
};
