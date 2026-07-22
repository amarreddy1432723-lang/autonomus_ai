'use client';

import { Bell, Search, Settings } from 'lucide-react';
import styles from './AppShell.module.css';

export type MissionStatus = 'idle' | 'planning' | 'running' | 'waiting' | 'failed';

type WorkspaceTopBarProps = {
  projectName?: string;
  repositoryName?: string;
  missionStatus?: MissionStatus;
  selectedModel?: string;
  userName?: string;
};

const statusLabel: Record<MissionStatus, string> = {
  idle: 'Ready',
  planning: 'Planning',
  running: 'Running',
  waiting: 'Waiting',
  failed: 'Needs attention',
};

export default function WorkspaceTopBar({
  projectName = 'Arceus Code',
  repositoryName = 'Workspace',
  missionStatus = 'idle',
  selectedModel = 'Auto',
  userName = 'VK',
}: WorkspaceTopBarProps) {
  return (
    <div className={styles.topBar}>
      <div className={styles.brandGroup}>
        <span className={styles.brandMark}>A</span>
        <span className={styles.brandText}>
          <strong>{projectName}</strong>
          <span>{repositoryName}</span>
        </span>
      </div>
      <label className={styles.searchBox}>
        <Search size={15} />
        <input placeholder="Search project, files, commands..." />
      </label>
      <div className={styles.topActions}>
        <span className={styles.statusPill}>
          <span className={styles.statusDot} />
          {statusLabel[missionStatus]}
        </span>
        <span className={styles.statusPill}>{selectedModel}</span>
        <button type="button" className={styles.iconButton} aria-label="Notifications">
          <Bell size={16} />
        </button>
        <button type="button" className={styles.iconButton} aria-label="Settings">
          <Settings size={16} />
        </button>
        <span className={styles.statusPill}>{userName}</span>
      </div>
    </div>
  );
}
