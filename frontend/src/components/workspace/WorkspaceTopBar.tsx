'use client';

import { Bell, ChevronDown, CircleHelp, GitBranch, Play, Plus, Search, Share2 } from 'lucide-react';
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
        <span className={styles.projectGlyph}>{repositoryName.slice(0, 2).toUpperCase()}</span>
        <span className={styles.brandText}>
          <strong>{repositoryName}</strong>
          <span>{projectName}</span>
        </span>
        <ChevronDown size={14} />
        <span className={styles.branchPill}>
          <GitBranch size={13} />
          main
          <ChevronDown size={12} />
        </span>
      </div>
      <label className={styles.searchBox}>
        <Search size={15} />
        <input placeholder="Search files, code, agents, docs..." />
        <kbd>Ctrl K</kbd>
      </label>
      <div className={styles.topActions}>
        <button type="button" className={styles.topButton}>
          <Plus size={15} />
          New
        </button>
        <button type="button" className={styles.topButton}>
          <Share2 size={15} />
          Share
        </button>
        <button type="button" className={styles.runButton}>
          <Play size={15} />
          Run
          <ChevronDown size={12} />
        </button>
        <span className={styles.statusPill}>
          <span className={styles.statusDot} />
          {statusLabel[missionStatus]}
        </span>
        <button type="button" className={styles.iconButton} aria-label="Notifications">
          <Bell size={16} />
        </button>
        <button type="button" className={styles.iconButton} aria-label="Help">
          <CircleHelp size={16} />
        </button>
        <span className={styles.avatarPill}>{userName}</span>
      </div>
    </div>
  );
}
