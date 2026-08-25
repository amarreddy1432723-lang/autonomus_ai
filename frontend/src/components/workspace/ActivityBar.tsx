'use client';

import { Activity, Cloud, FolderKanban, Settings, UserCircle } from 'lucide-react';
import { useWorkspaceLayoutStore, type PrimarySidebarView } from '../../stores/workspace-layout-store';
import styles from './AppShell.module.css';

const items: Array<{ id: PrimarySidebarView | 'mission-control' | 'settings'; label: string; icon: typeof FolderKanban }> = [
  { id: 'explorer', label: 'Workspace', icon: FolderKanban },
  { id: 'mission-control', label: 'Mission Control', icon: Activity },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export default function ActivityBar() {
  const activeSidebarView = useWorkspaceLayoutStore((state) => state.activeSidebarView);
  const sidebarVisible = useWorkspaceLayoutStore((state) => state.sidebarVisible);
  const toggleSidebar = useWorkspaceLayoutStore((state) => state.toggleSidebar);

  return (
    <nav className={styles.activityBar} aria-label="Workspace activity">
      <div className={styles.navBrand}>
        <img src="/arceus-logo.svg" alt="" aria-hidden="true" />
        <strong>Arceus Code</strong>
      </div>
      <div className={styles.navSection}>
      {items.map((item) => {
        const Icon = item.icon;
        const active = item.id === 'explorer' && sidebarVisible && activeSidebarView === item.id;
        return (
          <button
            key={item.id}
            type="button"
            className={styles.activityButton}
            data-active={active || undefined}
            title={item.label}
            aria-label={item.label}
            onClick={() => {
              if (item.id === 'explorer') toggleSidebar(item.id);
              if (item.id === 'mission-control') window.location.href = '/mission-control';
              if (item.id === 'settings') window.location.href = '/settings';
            }}
          >
            <Icon size={16} />
            <span>{item.label}</span>
          </button>
        );
      })}
      </div>
      <div className={styles.desktopShellMeta} aria-label="Arceus Code status">
        <button type="button" onClick={() => { window.location.href = '/settings'; }}>
          <UserCircle size={15} />
          <span>Account</span>
        </button>
        <div>
          <Cloud size={15} />
          <span>Connected</span>
        </div>
        <div>
          <span>Version</span>
          <strong>v1.0.0</strong>
        </div>
      </div>
    </nav>
  );
}
