import type { ReactNode } from 'react';
import styles from './ui.module.css';

type EmptyStateProps = {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
};

export function EmptyState({ action, description, icon, title }: EmptyStateProps) {
  return (
    <section className={styles.emptyState}>
      {icon && <span className={styles.emptyIcon}>{icon}</span>}
      <h2>{title}</h2>
      {description && <p>{description}</p>}
      {action}
    </section>
  );
}
