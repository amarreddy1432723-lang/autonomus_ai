const fs = require("fs");
const path = require("path");

const FINAL_STAGES = new Set(["completed", "abandoned"]);

function safeName(value) {
    return String(value || "unknown").replace(/[^a-zA-Z0-9_.-]/g, "_");
}

function nowIso() {
    return new Date().toISOString();
}

class ExecutionJournal {
    constructor({ journalDir, logger = console } = {}) {
        this.journalDir = journalDir || path.join(process.cwd(), ".arceus", "execution-journal");
        this.logger = logger;
    }

    async ensureDir() {
        await fs.promises.mkdir(this.journalDir, { recursive: true });
    }

    entryPath(assignmentId) {
        return path.join(this.journalDir, `${safeName(assignmentId)}.json`);
    }

    async write(entry) {
        if (!entry?.assignment_id) throw new Error("Journal entry requires assignment_id.");
        await this.ensureDir();
        const existing = await this.read(entry.assignment_id).catch(() => null);
        const merged = {
            ...(existing || {}),
            ...entry,
            started_at: entry.started_at || existing?.started_at || nowIso(),
            updated_at: nowIso(),
        };
        const temp = `${this.entryPath(entry.assignment_id)}.${process.pid}.tmp`;
        await fs.promises.writeFile(temp, JSON.stringify(merged, null, 2), "utf8");
        await fs.promises.rename(temp, this.entryPath(entry.assignment_id));
        return merged;
    }

    async update(assignmentId, patch) {
        const existing = await this.read(assignmentId);
        return this.write({ ...existing, ...patch, assignment_id: assignmentId });
    }

    async read(assignmentId) {
        const content = await fs.promises.readFile(this.entryPath(assignmentId), "utf8");
        return JSON.parse(content);
    }

    async listUnfinished() {
        await this.ensureDir();
        const files = await fs.promises.readdir(this.journalDir).catch(() => []);
        const entries = [];
        for (const file of files.filter((item) => item.endsWith(".json"))) {
            try {
                const content = await fs.promises.readFile(path.join(this.journalDir, file), "utf8");
                const entry = JSON.parse(content);
                if (!FINAL_STAGES.has(entry.stage)) entries.push(entry);
            } catch (error) {
                this.logger.warn?.("failed to read execution journal entry", error);
            }
        }
        return entries.sort((a, b) => String(a.updated_at || "").localeCompare(String(b.updated_at || "")));
    }

    async remove(assignmentId) {
        await fs.promises.rm(this.entryPath(assignmentId), { force: true });
    }
}

module.exports = {
    ExecutionJournal,
    FINAL_STAGES,
};
