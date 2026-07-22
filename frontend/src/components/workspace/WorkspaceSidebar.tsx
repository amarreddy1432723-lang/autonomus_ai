import type { ReactNode } from 'react';
import styles from './AppShell.module.css';

type WorkspaceSidebarProps = {
  title: string;
  action?: ReactNode;
  children: ReactNode;
};

export default function WorkspaceSidebar({ title, action, children }: WorkspaceSidebarProps) {
  return (
    <section className={styles.panelShell}>
      <header className={styles.panelHeader}>
        <span>{title}</span>
        {action}
      </header>
      <div className={styles.panelBody}>{children}</div>
    </section>
  );
}
