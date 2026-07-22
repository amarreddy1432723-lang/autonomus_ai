'use client';

import { Box, Files, GitBranch, Search, Settings, Target } from 'lucide-react';
import { useWorkspaceLayoutStore, type PrimarySidebarView } from '../../stores/workspace-layout-store';
import styles from './AppShell.module.css';

const items: Array<{ id: PrimarySidebarView | 'settings'; label: string; icon: typeof Files }> = [
  { id: 'explorer', label: 'Explorer', icon: Files },
  { id: 'search', label: 'Search', icon: Search },
  { id: 'source-control', label: 'Source Control', icon: GitBranch },
  { id: 'missions', label: 'Missions', icon: Target },
  { id: 'extensions', label: 'Extensions', icon: Box },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export default function ActivityBar() {
  const activeSidebarView = useWorkspaceLayoutStore((state) => state.activeSidebarView);
  const sidebarVisible = useWorkspaceLayoutStore((state) => state.sidebarVisible);
  const toggleSidebar = useWorkspaceLayoutStore((state) => state.toggleSidebar);

  return (
    <nav className={styles.activityBar} aria-label="Workspace activity">
      {items.map((item) => {
        const Icon = item.icon;
        const active = item.id !== 'settings' && sidebarVisible && activeSidebarView === item.id;
        return (
          <button
            key={item.id}
            type="button"
            className={styles.activityButton}
            data-active={active || undefined}
            title={item.label}
            aria-label={item.label}
            onClick={() => item.id !== 'settings' && toggleSidebar(item.id)}
          >
            <Icon size={16} />
          </button>
        );
      })}
    </nav>
  );
}
