import type { ReactNode } from 'react';
import styles from './AppShell.module.css';

type BottomPanelProps = {
  title: string;
  children: ReactNode;
};

export default function BottomPanel({ title, children }: BottomPanelProps) {
  return (
    <section className={styles.panelShell}>
      <header className={styles.panelHeader}>{title}</header>
      <div className={styles.panelBody}>{children}</div>
    </section>
  );
}
