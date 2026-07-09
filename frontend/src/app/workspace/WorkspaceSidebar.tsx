'use client';

import Link from 'next/link';
import { Code2, Files, FolderPlus, MessageSquarePlus, Search, Settings } from 'lucide-react';
import styles from './Workspace.module.css';

export type WorkspaceRecentItem = {
  id: string;
  label: string;
  detail?: string;
};

type Props = {
  recentItems: WorkspaceRecentItem[];
  busy?: boolean;
  onCreateProject: () => void;
  onNewChat: () => void;
  onSearch: () => void;
  onOpenFiles: () => void;
};

export default function WorkspaceSidebar({ recentItems, busy, onCreateProject, onNewChat, onSearch, onOpenFiles }: Props) {
  const items = recentItems.length
    ? recentItems
    : [
        { id: 'empty-project', label: 'No recent project yet', detail: 'Import files or a repo to begin' },
        { id: 'empty-chat', label: 'No recent chat yet', detail: 'Ask NEXUS to plan or edit' },
      ];

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
        <button type="button" onClick={onCreateProject} disabled={busy}>
          <FolderPlus size={16} />
          Create Project
        </button>
        <button type="button" onClick={onNewChat} disabled={busy}>
          <MessageSquarePlus size={16} />
          New Chat
        </button>
        <button type="button" onClick={onSearch}>
          <Search size={16} />
          Search
        </button>
      </div>

      <section className={styles.sidebarRecent} aria-label="Recent workspace items">
        <div className={styles.sidebarSectionLabel}>Recent</div>
        {items.slice(0, 8).map((item) => (
          <button className={styles.recentItem} key={item.id} type="button" onClick={onSearch} disabled={item.id.startsWith('empty-')}>
            <Code2 size={14} />
            <span>
              <strong>{item.label}</strong>
              {item.detail && <em>{item.detail}</em>}
            </span>
          </button>
        ))}
      </section>

      <div className={styles.sidebarUtilities}>
        <button className={styles.sidebarSettings} type="button" onClick={onOpenFiles}>
          <Files size={16} />
          Project Files
        </button>
        <Link className={styles.sidebarSettings} href="/settings">
          <Settings size={16} />
          Settings
        </Link>
      </div>
    </aside>
  );
}
