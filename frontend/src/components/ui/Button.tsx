import type { ButtonHTMLAttributes, ReactNode } from 'react';
import styles from './ui.module.css';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  icon?: ReactNode;
};

export function Button({ children, className = '', icon, variant = 'secondary', ...props }: ButtonProps) {
  return (
    <button className={`${styles.button} ${styles[`button_${variant}`]} ${className}`} type="button" {...props}>
      {icon}
      <span>{children}</span>
    </button>
  );
}
