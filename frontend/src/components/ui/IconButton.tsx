import type { ButtonHTMLAttributes, ReactNode } from 'react';
import styles from './ui.module.css';

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  children: ReactNode;
};

export function IconButton({ children, className = '', label, ...props }: IconButtonProps) {
  return (
    <button className={`${styles.iconButton} ${className}`} type="button" aria-label={label} title={label} {...props}>
      {children}
    </button>
  );
}
