const fs = require("fs");
const os = require("os");
const path = require("path");

const { executeProjectSummaryTask } = require("../desktop/runtime/controlled-task-executor");

function copyFixture(source, target) {
    fs.mkdirSync(target, { recursive: true });
    fs.cpSync(source, target, { recursive: true });
}

async function main() {
    const jsonOnly = process.argv.includes("--json");
    const repoRoot = path.resolve(__dirname, "..");
    const fixture = path.join(repoRoot, "tests", "fixtures", "sample-repository");
    if (!fs.existsSync(fixture)) {
        throw new Error(`Fixture repository not found: ${fixture}`);
    }
    const tempParent = fs.mkdtempSync(path.join(os.tmpdir(), "arceus-controlled-task-"));
    const disposableRepo = path.join(tempParent, "sample-repository");
    copyFixture(fixture, disposableRepo);

    const fixtureTarget = path.join(fixture, "PROJECT_SUMMARY.md");
    const disposableTarget = path.join(disposableRepo, "PROJECT_SUMMARY.md");
    if (fs.existsSync(fixtureTarget)) {
        throw new Error("Fixture repository already contains PROJECT_SUMMARY.md; controlled test requires a clean fixture.");
    }

    const result = await executeProjectSummaryTask(disposableRepo);
    const checks = [
        { name: "Controlled task completed", ok: result.status === "completed", detail: result.status },
        { name: "Evidence emitted", ok: result.evidence.length >= 10, detail: `${result.evidence.length} records` },
        { name: "Change set rolled back", ok: result.change_set.review_state === "rolled_back", detail: result.change_set.review_state },
        { name: "Disposable file removed", ok: !fs.existsSync(disposableTarget), detail: "PROJECT_SUMMARY.md absent after rollback" },
        { name: "Fixture untouched", ok: !fs.existsSync(fixtureTarget), detail: "source fixture stayed clean" },
    ];
    const failed = checks.filter((check) => !check.ok);
    const summary = {
        ok: failed.length === 0,
        disposable_repository: disposableRepo,
        checks,
        evidence: result.evidence,
        change_set: result.change_set,
        context: result.context,
        steps: result.steps,
    };
    if (jsonOnly) {
        process.stdout.write(`${JSON.stringify(summary)}\n`);
    } else {
        console.table(checks);
        console.log(JSON.stringify(summary, null, 2));
    }
    if (failed.length) {
        throw new Error(`Controlled desktop task failed: ${failed.map((check) => check.name).join(", ")}`);
    }
}

main().catch((error) => {
    console.error(error.message || error);
    process.exit(1);
});
