import type { InputHTMLAttributes } from 'react';
import styles from './ui.module.css';

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string;
};

export function Input({ className = '', hint, id, label, ...props }: InputProps) {
  return (
    <label className={styles.field} htmlFor={id}>
      {label && <span>{label}</span>}
      <input id={id} className={`${styles.input} ${className}`} {...props} />
      {hint && <em>{hint}</em>}
    </label>
  );
}
