import styles from './MissionControlProduct.module.css';
import type { MissionControlLock } from './types';

export function RepositoryLocks({ locks }: { locks: MissionControlLock[] }) {
  return (
    <section className={styles.panel} aria-label="Repository locks">
      <header>
        <div>
          <h3>Repository Locks</h3>
          <p>Path reservations prevent workers from editing the same files at the same time.</p>
        </div>
        <span className={styles.taskBadge}>{locks.length} active</span>
      </header>
      <div className={styles.lockList}>
        {locks.length === 0 && <div className={styles.empty}>No active repository locks.</div>}
        {locks.map((lock) => (
          <article key={lock.reservationId} className={styles.lockItem}>
            <strong>{lock.pathPattern}</strong>
            <small>{lock.reservationMode} · {lock.status} · {lock.taskKey || 'unassigned'}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
