const fs = require("fs");
const path = require("path");

function riskForCommand(command) {
    const text = String(command || "").toLowerCase();
    if (/\b(rm|del|rmdir|format|drop|truncate|deploy|push|publish)\b/.test(text)) return "high";
    if (/\b(install|add|migration|migrate|prisma|alembic|docker compose up)\b/.test(text)) return "moderate";
    return "low";
}

function task(id, label, command, cwd, group) {
    return {
        id,
        label,
        command,
        cwd,
        group,
        riskLevel: riskForCommand(command)
    };
}

function readJson(filePath) {
    try {
        return JSON.parse(fs.readFileSync(filePath, "utf8"));
    } catch {
        return null;
    }
}

function discoverWorkspaceTasks(rootPath) {
    const root = path.resolve(rootPath);
    const tasks = [];
    const packageJsonPath = path.join(root, "package.json");
    const packageJson = fs.existsSync(packageJsonPath) ? readJson(packageJsonPath) : null;
    if (packageJson?.scripts) {
        for (const [script, command] of Object.entries(packageJson.scripts)) {
            const group = script.includes("test") ? "test" : script.includes("lint") ? "lint" : script.includes("build") ? "build" : script.includes("dev") || script.includes("start") ? "run" : "custom";
            tasks.push(task(`npm:${script}`, `npm run ${script}`, `npm run ${script}`, root, group));
            if (script === "test" && command === "jest") {
                tasks[tasks.length - 1].command = "npm test";
            }
        }
    }
    if (fs.existsSync(path.join(root, "pyproject.toml")) || fs.existsSync(path.join(root, "pytest.ini"))) {
        tasks.push(task("python:pytest", "pytest", "python -m pytest", root, "test"));
    }
    if (fs.existsSync(path.join(root, "Makefile"))) {
        tasks.push(task("make:test", "make test", "make test", root, "test"));
        tasks.push(task("make:build", "make build", "make build", root, "build"));
    }
    if (fs.existsSync(path.join(root, "Cargo.toml"))) {
        tasks.push(task("cargo:test", "cargo test", "cargo test", root, "test"));
        tasks.push(task("cargo:build", "cargo build", "cargo build", root, "build"));
    }
    if (fs.existsSync(path.join(root, "go.mod"))) {
        tasks.push(task("go:test", "go test ./...", "go test ./...", root, "test"));
    }
    return tasks;
}

module.exports = {
    discoverWorkspaceTasks,
    riskForCommand
};

