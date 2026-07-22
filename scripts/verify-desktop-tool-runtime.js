const fs = require("fs");
const os = require("os");
const path = require("path");

const { getAuditLog, invokeTool, listTools } = require("../desktop/runtime/tool-registry");

async function main() {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "arceus-tools-"));
    fs.writeFileSync(path.join(root, "README.md"), "# Sample\nhello arceus\n", "utf8");
    fs.writeFileSync(
        path.join(root, "package.json"),
        JSON.stringify({ scripts: { test: "node -e \"process.exit(0)\"" } }, null, 2),
        "utf8"
    );

    const checks = [];
    const add = (name, ok, detail = "") => checks.push({ name, ok: Boolean(ok), detail });

    add("Tool registry", listTools().length >= 10, `${listTools().length} tools`);

    const read = await invokeTool("read_file", { repositoryRoot: root, path: "README.md" });
    add("read_file", read.ok && read.content.includes("hello arceus"), read.path || read.message);

    const directory = await invokeTool("read_directory", { repositoryRoot: root, path: "." });
    add("read_directory", directory.ok && directory.entries.some((entry) => entry.name === "README.md"), `${directory.entries?.length || 0} entries`);

    const search = await invokeTool("search_repository", { repositoryRoot: root, query: "arceus" });
    add("search_repository", search.ok && search.matches.length === 1, `${search.matches?.length || 0} matches`);

    const patch = await invokeTool("propose_patch", {
        repositoryRoot: root,
        path: "PROJECT_SUMMARY.md",
        operation: "create",
        modifiedContent: "Sample project summary\n",
    });
    add("propose_patch", patch.ok && patch.diff.includes("PROJECT_SUMMARY.md") && patch.applied === false, patch.message || patch.operation);

    const validation = await invokeTool("validate_patch", {
        repositoryRoot: root,
        path: "PROJECT_SUMMARY.md",
        operation: "create",
        modifiedContent: "Sample project summary\n",
    });
    add("validate_patch", validation.ok && validation.review_required === false, validation.message || validation.operation);

    const apply = await invokeTool("apply_patch", {
        repositoryRoot: root,
        path: "PROJECT_SUMMARY.md",
        operation: "create",
        modifiedContent: "Sample project summary\n",
    });
    add("apply_patch", apply.ok && apply.rollback_snapshot_id && fs.existsSync(path.join(root, "PROJECT_SUMMARY.md")), apply.path || apply.message);

    const rollback = await invokeTool("rollback_patch", {
        rollback_snapshot_id: apply.rollback_snapshot_id,
    });
    add("rollback_patch", rollback.ok && !fs.existsSync(path.join(root, "PROJECT_SUMMARY.md")), rollback.message || rollback.operation);

    const create = await invokeTool("create_file", {
        repositoryRoot: root,
        path: "PROJECT_SUMMARY.md",
        content: "Sample project summary\n",
    });
    add("create_file", create.ok && fs.existsSync(path.join(root, "PROJECT_SUMMARY.md")), create.path || create.message);

    const riskyDelete = await invokeTool("validate_patch", {
        repositoryRoot: root,
        path: "PROJECT_SUMMARY.md",
        operation: "delete",
    });
    add("risky patch review required", riskyDelete.ok === false && riskyDelete.error_class === "review_required", riskyDelete.message);

    const gitStatus = await invokeTool("git_status", { repositoryRoot: root });
    add("git_status", gitStatus.ok, gitStatus.stderr || "ok");

    const denied = await invokeTool("run_command", { repositoryRoot: root, command: "git", args: ["push"] });
    add("unsafe command denied", denied.ok === false && denied.error_class === "approval_required", denied.message);

    const outside = await invokeTool("read_file", { repositoryRoot: root, path: "../outside.txt" });
    add("outside path denied", outside.ok === false, outside.message);

    add("Audit records", getAuditLog().length >= 12, `${getAuditLog().length} records`);

    console.table(checks);
    const failed = checks.filter((check) => !check.ok);
    if (failed.length) {
        throw new Error(`Desktop tool runtime verification failed: ${failed.map((item) => item.name).join(", ")}`);
    }
    console.log(`Desktop tool runtime verification passed: ${root}`);
}

main().catch((error) => {
    console.error(error.message || error);
    process.exit(1);
});
