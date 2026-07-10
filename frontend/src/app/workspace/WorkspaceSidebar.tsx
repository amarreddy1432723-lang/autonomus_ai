'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Code2, Folder, FolderPlus, MessageSquarePlus, Search, Settings } from 'lucide-react';
import styles from './Workspace.module.css';

export type WorkspaceRecentItem = {
  id: string;
  label: string;
  detail?: string;
  kind?: 'project' | 'job' | 'file';
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
};

export default function WorkspaceSidebar({ recentItems, busy, onCreateProject, onNewChat, onSearch, onOpenRecent, onImportLocal, onToggleFiles, onToggleEditor, editorOpen }: Props) {
  const [isElectron, setIsElectron] = useState(false);
  const items = recentItems.length
    ? recentItems
    : [
        { id: 'empty-project', label: 'No recent project yet', detail: 'Import files or a repo to begin' },
        { id: 'empty-chat', label: 'No recent chat yet', detail: 'Ask NEXUS to plan or edit' },
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
        <span className={styles.sidebarLogo}>N</span>
        <div>
          <strong>NEXUS Code</strong>
          <span>Workspace</span>
        </div>
      </div>

      <div className={styles.sidebarActions}>
        {isElectron ? (
          <button type="button" onClick={openLocalFolder} disabled={busy}>
            <FolderPlus size={16} />
            Open Local Folder
          </button>
        ) : (
          <button type="button" onClick={onCreateProject} disabled={busy}>
            <FolderPlus size={16} />
            Create Project
          </button>
        )}
        <button type="button" onClick={onNewChat} disabled={busy}>
          <MessageSquarePlus size={16} />
          New Chat
        </button>
        <button type="button" onClick={onSearch}>
          <Search size={16} />
          Search
        </button>
        <button type="button" onClick={onToggleFiles} disabled={busy}>
          <Folder size={16} />
          Files Explorer
        </button>
        <button type="button" onClick={onToggleEditor}>
          <Code2 size={16} />
          {editorOpen ? 'Close Editor' : 'Open Editor'}
        </button>
      </div>

      <section className={styles.sidebarRecent} aria-label="Recent workspace items">
        <div className={styles.sidebarSectionLabel}>Recent</div>
        {items.slice(0, 8).map((item) => (
          <button className={styles.recentItem} key={item.id} type="button" onClick={() => onOpenRecent(item)} disabled={item.id.startsWith('empty-')}>
            <Code2 size={14} />
            <span>
              <strong>{item.label}</strong>
              {item.detail && <em>{item.detail}</em>}
            </span>
          </button>
        ))}
      </section>

      <div className={styles.sidebarUtilities}>
        <Link className={styles.sidebarSettings} href="/settings">
          <Settings size={16} />
          Settings
        </Link>
      </div>
    </aside>
  );
}
