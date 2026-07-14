# Core Concepts

## Projects

A project is the primary workspace boundary. Files, chats, jobs, patches, terminals, preview state, Git state, and activity belong to one project.

## Sessions

A session is a chat/work thread inside a project. New Chat creates a new session under the active project.

## Jobs

Jobs are durable units of background work: agent runs, checks, preview verification, GitHub operations, and sandbox commands.

## Patches

Patches are reviewable changes. Arceus supports create, modify, delete, rename, and folder operations. Users approve hunks/files before applying.

## Sandbox

Cloud/runtime commands should run in Docker sandbox mode for production. Electron trusted-folder mode runs local commands only inside the selected folder.

## Work Receipts

Work receipts summarize what Arceus did: inspected files, changed files, line impact, commands, checks, approval state, and next actions.
