const { executeProjectSummaryTask } = require("../controlled-task-executor");
const { invokeTool } = require("../tool-registry");
const { TaskExecutor } = require("./task-executor");

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
        throw new Error(`${label} failed: ${result.message || result.error_class || "unknown error"}`);
    }
}

class ControlledTaskExecutorAdapter extends TaskExecutor {
    async execute(context, hooks = {}) {
        const repositoryRoot = context.repositoryRoot;
        if (!repositoryRoot) throw new Error("repositoryRoot is required for desktop task execution.");
        await hooks.onStageChanged?.("executing");
        if (context.assignment.execution_class === "write_sensitive") {
            const result = await executeProjectSummaryTask(repositoryRoot, {
                path: context.targetPath || "PROJECT_SUMMARY.md",
            });
            for (const record of result.evidence || []) {
                await hooks.onEvidence?.(record);
            }
            if (result.change_set) await hooks.onChangeSet?.(result.change_set);
            await hooks.onProgress?.(100);
            return result;
        }

        const evidence = [];
        async function run(tool, input) {
            const result = await invokeTool(tool, input);
            const record = evidenceFrom(result, tool);
            evidence.push(record);
            await hooks.onEvidence?.(record);
            assertOk(tool, result);
            return result;
        }

        const directory = await run("read_directory", { repositoryRoot, path: "." });
        await hooks.onProgress?.(35);
        const packageJson = await run("read_file", { repositoryRoot, path: "package.json" });
        await hooks.onProgress?.(70);
        const search = await run("search_repository", { repositoryRoot, query: "FastAPI" });
        await hooks.onProgress?.(100);
        return {
            status: "completed",
            repository_root: repositoryRoot,
            evidence,
            context: {
                root_entries: directory.entries?.length || 0,
                package_sha256: packageJson.sha256,
                search_matches: search.matches?.length || 0,
            },
        };
    }
}

module.exports = {
    ControlledTaskExecutorAdapter,
};
