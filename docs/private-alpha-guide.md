# Arceus Code Private Alpha Guide

Welcome to the Arceus Code private Alpha. This build is for proving the core engineering loop, not broad production use.

## Install

1. Download the Windows installer from the Arceus download page.
2. Verify the SHA-256 checksum shown on the page when available.
3. Run the installer.
4. Launch Arceus Code from the desktop shortcut or Start Menu.

If Windows SmartScreen appears on an unsigned private build, choose **More info** and **Run anyway** only if the installer came from the official Alpha release link.

## Connect Account

1. Click **Connect account**.
2. Complete Clerk sign-in in the browser.
3. Return to Arceus Code.
4. Confirm the header shows connected account state.

Chrome login does not automatically mean the desktop app is signed in. The desktop must receive and store its own session.

## First Mission

Use a small repository first.

1. Click **Open Folder**.
2. Select a Git repository you can safely modify.
3. Open the terminal and run `git status`.
4. Ask Arceus for a low-risk task, such as:

```text
Add a short README section explaining how to run tests.
```

5. Watch Mission Control.
6. Review evidence and changed files.
7. Click **Undo changes** to verify rollback.
8. Repeat and keep the change if the proof looks correct.

## Feedback

Send feedback with:

- What you expected.
- What happened.
- Screenshot or short screen recording if useful.
- Exported diagnostics JSON when the issue is technical.
- Repository type and language.

Do not include private source code, production secrets, customer data, or API keys in feedback.

## Export Diagnostics

In the desktop app, use **Settings** or **Diagnostics** and click **Export Logs**. The exported JSON is redacted and includes app logs, crash markers, version, platform, and service state.

## Good Alpha Test Scenarios

- Open an existing Next.js repository.
- Open an existing Python/FastAPI repository.
- Run terminal commands in the repository.
- Ask for documentation-only changes.
- Ask for small test additions.
- Ask for a risky delete and confirm it goes to review instead of auto-applying.
- Force a failed test and confirm Mission Control blocks completion.
- Restart while a mission is running and confirm recovery state is understandable.
