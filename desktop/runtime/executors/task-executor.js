class TaskExecutor {
    async prepare() {}

    async execute() {
        throw new Error("TaskExecutor.execute must be implemented.");
    }

    async cancel() {}

    async cleanup() {}
}

module.exports = {
    TaskExecutor,
};
