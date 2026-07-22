'use client';

import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from 'react';
import { useCallback } from 'react';
import { useWorkspaceLayoutStore } from '../../stores/workspace-layout-store';
import styles from './AppShell.module.css';

type AppShellProps = {
  topBar?: ReactNode;
  activityBar?: ReactNode;
  sidebar?: ReactNode;
  editor?: ReactNode;
  assistant?: ReactNode;
  bottomPanel?: ReactNode;
  statusBar?: ReactNode;
  className?: string;
};

export default function AppShell({
  topBar,
  activityBar,
  sidebar,
  editor,
  assistant,
  bottomPanel,
  statusBar,
  className,
}: AppShellProps) {
  const layout = useWorkspaceLayoutStore();
  const setSidebarWidth = useWorkspaceLayoutStore((state) => state.setSidebarWidth);
  const setAIPanelWidth = useWorkspaceLayoutStore((state) => state.setAIPanelWidth);
  const setBottomPanelHeight = useWorkspaceLayoutStore((state) => state.setBottomPanelHeight);
  const shellStyle = {
    '--workspace-sidebar-width': `${layout.sidebarWidth}px`,
    '--workspace-ai-panel-width': `${layout.aiPanelWidth}px`,
    '--workspace-bottom-panel-height': `${layout.bottomPanelHeight}px`,
  } as CSSProperties;

  const startResize = useCallback(
    (target: 'sidebar' | 'ai' | 'bottom', event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      const startX = event.clientX;
      const startY = event.clientY;
      const startSidebar = layout.sidebarWidth;
      const startAI = layout.aiPanelWidth;
      const startBottom = layout.bottomPanelHeight;

      function onMove(moveEvent: PointerEvent) {
        if (target === 'sidebar') setSidebarWidth(startSidebar + moveEvent.clientX - startX);
        if (target === 'ai') setAIPanelWidth(startAI + startX - moveEvent.clientX);
        if (target === 'bottom') setBottomPanelHeight(startBottom + startY - moveEvent.clientY);
      }

      function onUp() {
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }

      document.body.style.cursor = target === 'bottom' ? 'row-resize' : 'col-resize';
      document.body.style.userSelect = 'none';
      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp, { once: true });
    },
    [layout.aiPanelWidth, layout.bottomPanelHeight, layout.sidebarWidth, setAIPanelWidth, setBottomPanelHeight, setSidebarWidth],
  );

  return (
    <div
      className={[styles.shell, className].filter(Boolean).join(' ')}
      style={shellStyle}
      data-sidebar-visible={layout.sidebarVisible}
      data-ai-visible={layout.aiPanelVisible}
      data-bottom-visible={layout.bottomPanelVisible}
    >
      <div className={styles.topBarSlot}>{topBar}</div>
      <div className={styles.main}>
        <div className={styles.activitySlot}>{activityBar}</div>
        <aside className={styles.sidebarSlot}>
          {sidebar}
          <div className={styles.resizeHandleVertical} role="separator" aria-label="Resize sidebar" onPointerDown={(event) => startResize('sidebar', event)} />
        </aside>
        <section className={styles.center}>
          <div className={styles.editorSlot}>{editor}</div>
          <div className={styles.bottomSlot}>
            <div className={styles.resizeHandleHorizontal} role="separator" aria-label="Resize bottom panel" onPointerDown={(event) => startResize('bottom', event)} />
            {bottomPanel}
          </div>
        </section>
        <aside className={styles.assistantSlot}>
          <div className={styles.resizeHandleVerticalLeft} role="separator" aria-label="Resize AI panel" onPointerDown={(event) => startResize('ai', event)} />
          {assistant}
        </aside>
      </div>
      <footer className={styles.statusSlot}>{statusBar}</footer>
    </div>
  );
}
