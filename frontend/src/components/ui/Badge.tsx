import type { HTMLAttributes, ReactNode } from 'react';
import styles from './Badge.module.css';

type BadgeTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  leadingIcon?: ReactNode;
}

export function Badge({ tone = 'neutral', leadingIcon, className, children, ...props }: BadgeProps) {
  const classes = [styles.badge, tone !== 'neutral' ? styles[tone] : '', className].filter(Boolean).join(' ');
  return (
    <span className={classes} {...props}>
      {leadingIcon}
      {children}
    </span>
  );
}

