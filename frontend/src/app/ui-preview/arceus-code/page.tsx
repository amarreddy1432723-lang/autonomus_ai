import { notFound } from 'next/navigation';

type PreviewButton = {
  label: string;
  behavior: string;
  state?: 'enabled' | 'disabled' | 'warning' | 'primary';
  dependency?: string;
};

type PreviewScene = {
  title: string;
  image: string;
  intent: string;
  buttons: PreviewButton[];
};

const scenes: PreviewScene[] = [
  {
    title: 'Desktop shell signed out',
    image: '01-desktop-shell-signed-out.png',
    intent: 'Code-only desktop header with account connection, no Product Hub or PA/Interview links.',
    buttons: [
      { label: 'Connect account', behavior: 'Open desktop auth handoff.', state: 'primary', dependency: 'Clerk desktop token' },
      { label: 'Retry services', behavior: 'Refresh /api/v1/ready state.', dependency: 'agent-service' },
      { label: 'Open Folder', behavior: 'Open native folder picker.', dependency: 'Electron IPC' },
    ],
  },
  {
    title: 'Desktop shell signed in',
    image: '02-desktop-shell-signed-in.png',
    intent: 'Authenticated Code workspace shell with avatar menu and clean command search.',
    buttons: [
      { label: 'Avatar', behavior: 'Open account menu.', dependency: 'Clerk user' },
      { label: 'Command search', behavior: 'Open command/search palette.' },
      { label: 'Notifications', behavior: 'Show Code-only issues and approvals.' },
    ],
  },
  {
    title: 'API offline local mode',
    image: '03-api-offline-local-mode.png',
    intent: 'Agent API offline while local files, editor, and terminal remain usable.',
    buttons: [
      { label: 'Use local terminal', behavior: 'Open bottom terminal bound to trusted folder.', state: 'primary', dependency: 'Electron PTY' },
      { label: 'Retry services', behavior: 'Retry backend health checks.', state: 'warning', dependency: '/api/v1/ready' },
      { label: 'Cloud agent', behavior: 'Disabled until agent-service is online.', state: 'disabled', dependency: 'agent-service' },
    ],
  },
  {
    title: 'Workspace empty',
    image: '04-workspace-empty.png',
    intent: 'First launch state that pushes users to open a folder or describe a task.',
    buttons: [
      { label: 'Open Folder', behavior: 'Create or reopen trusted local project.', state: 'primary', dependency: 'Electron IPC' },
      { label: 'New Chat', behavior: 'Create project-scoped chat.', state: 'disabled', dependency: 'active project' },
      { label: 'Plan', behavior: 'Prepare a scoped task before execution.' },
    ],
  },
  {
    title: 'Open folder file tree',
    image: '05-open-folder-file-tree.png',
    intent: 'Explorer drawer showing source-of-truth folder tree, ignored paths hidden, dirty dots visible.',
    buttons: [
      { label: 'New File', behavior: 'Create file in selected folder.', dependency: 'trusted workspace' },
      { label: 'Rename', behavior: 'Inline rename with path safety checks.', dependency: 'Electron file IPC' },
      { label: 'Reveal', behavior: 'Reveal item in system file explorer.', dependency: 'Electron shell' },
    ],
  },
  {
    title: 'Editor chat terminal',
    image: '06-editor-chat-terminal.png',
    intent: 'Main Code loop: editor and chat above a VS Code-style bottom terminal.',
    buttons: [
      { label: 'Open terminal', behavior: 'Toggle bottom terminal.', state: 'primary', dependency: 'Electron PTY or backend fallback' },
      { label: 'Run checks', behavior: 'Run configured build/lint/test.' },
      { label: 'Toggle Editor', behavior: 'Show or hide Monaco editor.' },
    ],
  },
  {
    title: 'Agent receipt auto-applied',
    image: '07-agent-work-receipt-auto-applied.png',
    intent: 'Safe create/modify/folder changes apply immediately, with Undo as the trust control.',
    buttons: [
      { label: 'Undo changes', behavior: 'Rollback latest snapshot.', state: 'primary', dependency: 'rollback snapshot' },
      { label: 'Open changed files', behavior: 'Open changed files in editor tabs.' },
      { label: 'Create PR', behavior: 'Open Git flow for approved/applied changes.', dependency: 'GitHub App' },
    ],
  },
  {
    title: 'Risky change review required',
    image: '08-risky-change-review-required.png',
    intent: 'Delete, rename, stale hash, or conflict changes move to review instead of auto-apply.',
    buttons: [
      { label: 'Accept hunk', behavior: 'Mark hunk accepted.', state: 'warning' },
      { label: 'Reject hunk', behavior: 'Mark hunk rejected.' },
      { label: 'Apply selected', behavior: 'Apply only accepted hunks.', dependency: 'fresh file hashes' },
    ],
  },
  {
    title: 'Jobs drawer',
    image: '09-jobs-drawer.png',
    intent: 'Durable job control with compact rows and no dashboard bloat.',
    buttons: [
      { label: 'Pause', behavior: 'Pause/revoke running job.', dependency: 'worker queue' },
      { label: 'Cancel', behavior: 'Cancel queued or running job.' },
      { label: 'Retry', behavior: 'Requeue failed job.', dependency: 'job payload' },
    ],
  },
  {
    title: 'Preview verification',
    image: '10-preview-verification.png',
    intent: 'Preview iframe plus screenshot, console, network, and blank-page evidence.',
    buttons: [
      { label: 'Start preview', behavior: 'Start dev server/runtime.', dependency: 'sandbox/runtime' },
      { label: 'Re-verify', behavior: 'Run Playwright verification.', dependency: 'preview URL' },
      { label: 'Fix preview issue', behavior: 'Send evidence to agent for patch.', state: 'warning', dependency: 'verification errors' },
    ],
  },
  {
    title: 'Git PR flow',
    image: '11-git-pr-flow.png',
    intent: 'Repo picker, branch, commit approved changes only, PR, and CI checks.',
    buttons: [
      { label: 'Connect GitHub', behavior: 'Start GitHub App installation.', dependency: 'GitHub App' },
      { label: 'Commit approved changes', behavior: 'Commit only applied/accepted hunks.', dependency: 'fresh patch state' },
      { label: 'Open PR', behavior: 'Create PR and poll checks.', state: 'primary', dependency: 'branch + commit' },
    ],
  },
  {
    title: 'Settings code',
    image: '12-settings-code.png',
    intent: 'Desktop-only Code settings, not suite-wide PA/Interview/Admin controls.',
    buttons: [
      { label: 'Refresh', behavior: 'Reload local/backend status.' },
      { label: 'Save preferences', behavior: 'Persist Code workspace defaults.' },
      { label: 'Reconnect account', behavior: 'Restart desktop auth handoff.', dependency: 'Clerk token' },
    ],
  },
  {
    title: 'Settings AI models',
    image: '13-settings-ai-models.png',
    intent: 'Model router controls for local/cloud providers and task-specific selection.',
    buttons: [
      { label: 'Refresh models', behavior: 'Reload local and cloud model inventory.' },
      { label: 'Test local model', behavior: 'Run local provider smoke test.', dependency: 'Ollama/local runtime' },
      { label: 'Connect provider', behavior: 'Open provider credential flow.', dependency: 'encrypted vault' },
    ],
  },
  {
    title: 'Settings privacy vault',
    image: '14-settings-privacy-vault.png',
    intent: 'Local secret vault states for provider keys and privacy controls.',
    buttons: [
      { label: 'Create vault', behavior: 'Initialize encrypted local vault.' },
      { label: 'Unlock', behavior: 'Unlock vault for current session.' },
      { label: 'Lock', behavior: 'Clear decrypted keys from memory.' },
    ],
  },
  {
    title: 'Download page',
    image: '15-download-page.png',
    intent: 'Real installer state with checksum and release notes.',
    buttons: [
      { label: 'Download Windows Installer', behavior: 'Download signed or private test installer.', state: 'primary', dependency: 'release manifest URL' },
      { label: 'Copy SHA256', behavior: 'Copy checksum.', dependency: 'checksum configured' },
      { label: 'View release notes', behavior: 'Open GitHub release notes.', dependency: 'release URL' },
    ],
  },
];

const stateColors = {
  enabled: '#202634',
  disabled: '#3a2630',
  warning: '#3a3018',
  primary: '#32256f',
};

export default function ArceusCodeUiPreviewPage() {
  if (process.env.NODE_ENV === 'production' && process.env.NEXT_PUBLIC_ENABLE_UI_PREVIEWS !== 'true') {
    notFound();
  }

  return (
    <main style={{ minHeight: '100vh', background: '#08090e', color: '#f5f7fb', padding: 32, fontFamily: 'Inter, system-ui, sans-serif' }}>
      <section style={{ maxWidth: 1280, margin: '0 auto', display: 'grid', gap: 24 }}>
        <div style={{ display: 'grid', gap: 10 }}>
          <p style={{ color: '#9b8cff', fontWeight: 900, letterSpacing: 1, textTransform: 'uppercase', fontSize: 12 }}>Arceus Code UI Preview</p>
          <h1 style={{ fontSize: 38, margin: 0 }}>Desktop proof-first workspace storyboard</h1>
          <p style={{ color: '#9ca3af', maxWidth: 840, margin: 0, lineHeight: 1.6 }}>
            Development-only harness for auditing every main page and button state before implementation.
            PNG references live in <code>docs/ui-previews</code>; behavior rules live in <code>docs/ui-previews/button-state-audit.md</code>.
          </p>
        </div>

        <div style={{ border: '1px solid #202634', background: '#11141c', borderRadius: 12, padding: 16, display: 'grid', gap: 12 }}>
          <strong>Global implementation rules</strong>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 10 }}>
            {['Electron shows Arceus Code only', 'Logo opens /workspace', 'Terminal opens bottom panel', 'Right rail is icon-first', 'Offline keeps local files usable', 'Dangerous actions require review'].map((rule) => (
              <span key={rule} style={{ border: '1px solid #252b3a', borderRadius: 8, padding: '10px 12px', color: '#c9cfda', background: '#0d1017' }}>{rule}</span>
            ))}
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 14 }}>
          {scenes.map((scene, index) => (
            <article key={scene.image} style={{ border: '1px solid #202634', background: '#11141c', borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ borderBottom: '1px solid #202634', padding: 14, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <strong style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ display: 'grid', placeItems: 'center', width: 26, height: 26, borderRadius: 999, background: '#7c6cf0', color: 'white', fontSize: 12 }}>{index + 1}</span>
                  {scene.title}
                </strong>
                <code style={{ color: '#9ca3af', fontSize: 11 }}>{scene.image}</code>
              </div>
              <div style={{ padding: 14, display: 'grid', gap: 12 }}>
                <p style={{ color: '#aeb5c3', margin: 0, lineHeight: 1.55 }}>{scene.intent}</p>
                <div style={{ display: 'grid', gap: 8 }}>
                  {scene.buttons.map((button) => {
                    const state = button.state ?? 'enabled';
                    return (
                      <div key={`${scene.image}-${button.label}`} style={{ border: '1px solid #242b3a', borderLeft: `3px solid ${state === 'primary' ? '#8b78ff' : state === 'warning' ? '#d7a83f' : state === 'disabled' ? '#e05b70' : '#4b5565'}`, borderRadius: 8, padding: 10, background: stateColors[state] }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                          <strong>{button.label}</strong>
                          <span style={{ color: '#9ca3af', fontSize: 11, textTransform: 'uppercase' }}>{state}</span>
                        </div>
                        <p style={{ color: '#c5cad5', margin: '6px 0 0', fontSize: 13, lineHeight: 1.45 }}>{button.behavior}</p>
                        {button.dependency && <p style={{ color: '#8f98aa', margin: '6px 0 0', fontSize: 12 }}>Dependency: {button.dependency}</p>}
                      </div>
                    );
                  })}
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
