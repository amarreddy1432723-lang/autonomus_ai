import type { HTMLAttributes } from 'react';
import styles from './ui.module.css';

type BadgeTone = 'neutral' | 'success' | 'warning' | 'error' | 'info';

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: BadgeTone;
};

export function Badge({ children, className = '', tone = 'neutral', ...props }: BadgeProps) {
  return (
    <span className={`${styles.badge} ${styles[`badge_${tone}`]} ${className}`} {...props}>
      {children}
    </span>
  );
}
