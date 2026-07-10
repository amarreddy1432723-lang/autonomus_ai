'use client';

import { Bot, Calendar, Cloud, GitBranch, Globe, Mail, Play, RefreshCw, Settings, Terminal, Zap } from 'lucide-react';
import Link from 'next/link';
import type { GitHubStatus, RuntimeStatus } from './ActivityPanel';
import styles from './Workspace.module.css';

type WorkspaceApp = {
  id: string;
  name: string;
  detail: string;
  status: string;
  icon: typeof GitBranch;
  action?: string;
  onAction?: () => void;
  disabled?: boolean;
};

type Props = {
  githubStatus: GitHubStatus | null;
  runtimeStatus: RuntimeStatus | null;
  busy: boolean;
  onConnectGithub: () => void;
  onRefreshGithub: () => void;
  onSyncRuntime: () => void;
  onRunChecks: () => void;
};

export default function WorkspaceAppsPanel({
  githubStatus,
  runtimeStatus,
  busy,
  onConnectGithub,
  onRefreshGithub,
  onSyncRuntime,
  onRunChecks,
}: Props) {
  const apps: WorkspaceApp[] = [
    {
      id: 'github',
      name: 'GitHub',
      detail: githubStatus?.connected ? `${githubStatus.account?.login || 'Connected'} · repo import, branches, commits, PRs` : 'Install the NEXUS GitHub App to import repos and open PRs.',
      status: githubStatus?.connected ? 'Connected' : githubStatus?.configured ? 'Ready' : 'Setup needed',
      icon: GitBranch,
      action: githubStatus?.connected ? 'Refresh' : 'Connect',
      onAction: githubStatus?.connected ? onRefreshGithub : onConnectGithub,
      disabled: busy,
    },
    {
      id: 'runtime',
      name: 'Workspace Runtime',
      detail: `Runs safe CLI commands through the selected sandbox. Current provider: ${runtimeStatus?.provider || 'local'}.`,
      status: runtimeStatus?.status || 'Not synced',
      icon: Terminal,
      action: 'Sync runtime',
      onAction: onSyncRuntime,
      disabled: busy,
    },
    {
      id: 'checks',
      name: 'Checks',
      detail: 'Build, test, lint, and typecheck commands are routed through workspace command policies.',
      status: runtimeStatus?.last_command?.status || 'Ready',
      icon: Play,
      action: 'Run checks',
      onAction: onRunChecks,
      disabled: busy,
    },
    {
      id: 'browser',
      name: 'Browser Preview',
      detail: 'Use preview checks for screenshots, console errors, failed network requests, and visual fixes.',
      status: runtimeStatus?.preview?.status || 'Stopped',
      icon: Globe,
    },
    {
      id: 'deploy',
      name: 'Railway / Vercel',
      detail: 'Deployment providers stay internal to the workspace deploy agent and approval flow.',
      status: 'Internal',
      icon: Cloud,
    },
    {
      id: 'mail',
      name: 'Gmail / Outlook',
      detail: 'Optional PA-style email connectors can be added later without mixing products.',
      status: 'Available later',
      icon: Mail,
    },
    {
      id: 'calendar',
      name: 'Calendar',
      detail: 'Calendar connectors remain separate from NEXUS Code unless a workspace task explicitly needs them.',
      status: 'Available later',
      icon: Calendar,
    },
    {
      id: 'agent',
      name: 'NEXUS Agent CLI',
      detail: 'Internal agent actions call approved app CLIs and APIs server-side; tokens never appear in the browser.',
      status: 'Policy gated',
      icon: Bot,
    },
  ];

  return (
    <aside className={styles.appsPanel}>
      <div className={styles.panelHeader}>
        <span>Apps / Connectors</span>
        <Zap size={13} />
      </div>
      <div className={styles.appsList}>
        <div className={styles.appsIntro}>
          <strong>Connect apps once. Let NEXUS call them internally.</strong>
          <span>GitHub, runtime commands, browser preview, and deploy tools can be routed through workspace policies instead of manual sidebars.</span>
        </div>
        {apps.map((app) => {
          const Icon = app.icon;
          return (
            <div className={styles.appCard} key={app.id}>
              <div className={styles.appIcon}>
                <Icon size={14} />
              </div>
              <div className={styles.appBody}>
                <div className={styles.appTitleRow}>
                  <strong>{app.name}</strong>
                  <em>{app.status}</em>
                </div>
                <p>{app.detail}</p>
                {app.action && app.onAction && (
                  <button type="button" onClick={app.onAction} disabled={app.disabled}>
                    {app.action === 'Refresh' && <RefreshCw size={12} />}
                    {app.action}
                  </button>
                )}
              </div>
            </div>
          );
        })}
        <Link className={styles.appsSettingsLink} href="/settings">
          <Settings size={13} />
          Manage app connections
        </Link>
      </div>
    </aside>
  );
}
