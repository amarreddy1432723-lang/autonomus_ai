'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Code2, Folder, FolderPlus, GitMerge, MessageSquarePlus, Search, Settings, Trash2, X } from 'lucide-react';
import styles from './Workspace.module.css';

export type WorkspaceRecentItem = {
  id: string;
  label: string;
  detail?: string;
  kind?: 'project' | 'job' | 'file' | 'task';
};

type Props = {
  recentItems: WorkspaceRecentItem[];
  busy?: boolean;
  onCreateProject: () => void;
  onNewChat: () => void;
  onSearch: () => void;
  onOpenRecent: (item: WorkspaceRecentItem) => void;
  onImportLocal?: (path: string) => void;
  onToggleFiles?: () => void;
  onToggleEditor?: () => void;
  editorOpen?: boolean;
  activeProjectId?: string;
  mergeSelection?: string[];
  onToggleMergeProject?: (projectId: string) => void;
  onMergeSelectedProjects?: () => void;
  onCloseProject?: (projectId: string) => void;
  onRemoveProject?: (projectId: string) => void;
};

export default function WorkspaceSidebar({
  recentItems,
  busy,
  onCreateProject,
  onNewChat,
  onSearch,
  onOpenRecent,
  onImportLocal,
  onToggleFiles,
  onToggleEditor,
  activeProjectId,
  mergeSelection = [],
  onToggleMergeProject,
  onMergeSelectedProjects,
  onCloseProject,
  onRemoveProject,
}: Props) {
  const [isElectron, setIsElectron] = useState(false);
  const items = recentItems.length
    ? recentItems
    : [
        { id: 'empty-project', label: 'No recent project yet', detail: 'Import files or a repo to begin' },
        { id: 'empty-chat', label: 'No recent chat yet', detail: 'Ask Arceus to plan or edit' },
      ];

  useEffect(() => {
    setIsElectron(typeof window !== 'undefined' && Boolean((window as any).electron));
  }, []);

  const openLocalFolder = async () => {
    const electron = (window as any).electron;
    if (!electron?.selectDirectory || !onImportLocal) return;
    const path = await electron.selectDirectory();
    if (path) onImportLocal(path);
  };

  return (
    <aside className={styles.workspaceSidebar}>
      <div className={styles.sidebarBrand}>
        <span className={styles.sidebarLogo}>A</span>
        <div>
          <strong>Arceus Code</strong>
          <span>Workspace</span>
        </div>
      </div>

      <div className={styles.sidebarActions}>
        {isElectron ? (
          <button type="button" onClick={openLocalFolder} disabled={busy}>
            <FolderPlus size={13} />
            Open Folder
          </button>
        ) : (
          <button type="button" onClick={onCreateProject} disabled={busy}>
            <FolderPlus size={13} />
            Open Folder
          </button>
        )}
        <button type="button" onClick={onNewChat} disabled={busy}>
          <MessageSquarePlus size={13} />
          New Chat
        </button>
        <button type="button" onClick={onSearch}>
          <Search size={13} />
          Search
        </button>
        <button type="button" onClick={onToggleFiles} disabled={busy}>
          <Folder size={13} />
          Explorer
        </button>
        <button type="button" onClick={onToggleEditor}>
          <Code2 size={13} />
          Toggle Editor
        </button>
      </div>

      <section className={styles.sidebarRecent} aria-label="Recent workspace items">
        <div className={styles.sidebarSectionLabel}>Recent</div>
        {items.slice(0, 8).map((item) => {
          const projectId = item.id.replace(/^project-/, '');
          const isProject = item.kind === 'project';
          const isActive = isProject && projectId === activeProjectId;
          const selectedForMerge = isProject && mergeSelection.includes(projectId);
          return (
            <div className={`${styles.recentItemWrap} ${isActive ? styles.recentItemActive : ''}`} key={item.id}>
              <button className={styles.recentItem} type="button" onClick={() => onOpenRecent(item)} disabled={item.id.startsWith('empty-')}>
                <Code2 size={13} />
                <span>
                  <strong>{item.label}</strong>
                  {item.detail && <em>{item.detail}</em>}
                </span>
              </button>
              {isProject && (
                <div className={styles.recentActions}>
                  <button
                    type="button"
                    title={selectedForMerge ? 'Selected for merge' : 'Select for merge'}
                    className={selectedForMerge ? styles.recentActionActive : styles.recentAction}
                    onClick={() => onToggleMergeProject?.(projectId)}
                  >
                    <GitMerge size={12} />
                  </button>
                  <button type="button" title="Close project tab" className={styles.recentAction} onClick={() => onCloseProject?.(projectId)}>
                    <X size={12} />
                  </button>
                  <button type="button" title="Remove from app" className={styles.recentActionDanger} onClick={() => onRemoveProject?.(projectId)}>
                    <Trash2 size={12} />
                  </button>
                </div>
              )}
            </div>
          );
        })}
        {mergeSelection.length > 0 && (
          <button
            type="button"
            className={styles.mergeSelectedButton}
            disabled={mergeSelection.length !== 2 || busy}
            onClick={onMergeSelectedProjects}
          >
            <GitMerge size={13} />
            Merge {mergeSelection.length}/2 selected
          </button>
        )}
      </section>

      <div className={styles.sidebarUtilities}>
        <Link className={styles.sidebarSettings} href="/settings">
          <Settings size={13} />
          Settings
        </Link>
      </div>
    </aside>
  );
}
