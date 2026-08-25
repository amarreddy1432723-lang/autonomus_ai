import { AlertTriangle, CheckCircle2, Info } from 'lucide-react';
import styles from './MissionControlProduct.module.css';

export type MissionNotification = {
  id: string;
  tone: 'info' | 'success' | 'warning';
  title: string;
  detail: string;
};

export function MissionNotifications({ items }: { items: MissionNotification[] }) {
  if (!items.length) return null;
  return (
    <section className={styles.notificationStack} aria-label="Mission notifications">
      {items.map((item) => (
        <article key={item.id} data-tone={item.tone}>
          <span>{item.tone === 'success' ? <CheckCircle2 size={15} /> : item.tone === 'warning' ? <AlertTriangle size={15} /> : <Info size={15} />}</span>
          <div>
            <strong>{item.title}</strong>
            <small>{item.detail}</small>
          </div>
        </article>
      ))}
    </section>
  );
}
