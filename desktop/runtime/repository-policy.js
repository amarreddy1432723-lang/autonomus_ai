const fs = require("fs");
const path = require("path");

const DEFAULT_IGNORED_DIRS = new Set([
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".turbo",
    ".cache"
]);

const SYSTEM_DIR_PATTERNS = [
    /^windows$/i,
    /^program files$/i,
    /^program files \(x86\)$/i,
    /^system32$/i,
];

function normalizeRelative(relativePath = "") {
    const value = String(relativePath || "").replace(/\\/g, "/").replace(/^\/+/, "");
    if (value.includes("\0")) {
        throw new Error("Path contains an invalid character.");
    }
    return value || ".";
}

async function realpathIfExists(targetPath) {
    return fs.promises.realpath(targetPath).catch(() => targetPath);
}

async function resolveRepositoryPath(repositoryRoot, relativePath = "") {
    if (!repositoryRoot) {
        throw new Error("Repository root is required.");
    }
    const root = path.resolve(String(repositoryRoot));
    const rootReal = await realpathIfExists(root);
    const normalized = normalizeRelative(relativePath);
    const target = path.resolve(rootReal, normalized);
    const targetParent = await realpathIfExists(path.dirname(target));
    const candidate = path.resolve(targetParent, path.basename(target));
    const relative = path.relative(rootReal, candidate);
    if (relative.startsWith("..") || path.isAbsolute(relative)) {
        throw new Error("Path is outside the repository root.");
    }
    return {
        root: rootReal,
        target: candidate,
        relative: relative.replace(/\\/g, "/") || ".",
    };
}

function isIgnoredRelativePath(relativePath, options = {}) {
    const ignoredDirs = new Set([...(options.ignoredDirs || []), ...DEFAULT_IGNORED_DIRS]);
    const normalized = String(relativePath || "").replace(/\\/g, "/");
    if (!normalized || normalized === ".") return false;
    const parts = normalized.split("/");
    return parts.some((part) => ignoredDirs.has(part) || SYSTEM_DIR_PATTERNS.some((pattern) => pattern.test(part)));
}

async function assertRepositoryAllowed(repositoryRoot, relativePath = "", options = {}) {
    const resolved = await resolveRepositoryPath(repositoryRoot, relativePath);
    if (resolved.relative !== "." && isIgnoredRelativePath(resolved.relative, options)) {
        throw new Error(`Path is ignored or protected: ${resolved.relative}`);
    }
    return resolved;
}

async function assertRepositoryRoot(repositoryRoot) {
    const root = path.resolve(String(repositoryRoot || ""));
    const stat = await fs.promises.stat(root);
    if (!stat.isDirectory()) {
        throw new Error("Repository root must be a directory.");
    }
    return realpathIfExists(root);
}

module.exports = {
    DEFAULT_IGNORED_DIRS,
    assertRepositoryAllowed,
    assertRepositoryRoot,
    isIgnoredRelativePath,
    normalizeRelative,
    resolveRepositoryPath,
};

