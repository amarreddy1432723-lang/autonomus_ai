import styles from './MissionControlProduct.module.css';
import type { MissionControlRecovery } from './types';

export function RecoveryCenter({ recovery }: { recovery: MissionControlRecovery[] }) {
  return (
    <section className={styles.panel} aria-label="Recovery center">
      <header>
        <div>
          <h3>Recovery Center</h3>
          <p>Crash-safe checkpoints, stalled assignments, and recommended recovery actions.</p>
        </div>
        <span className={styles.taskBadge}>{recovery.length} reports</span>
      </header>
      <div className={styles.recoveryList}>
        {recovery.length === 0 && <div className={styles.empty}>No recovery action is needed.</div>}
        {recovery.map((item) => (
          <article key={item.assignmentId} className={styles.recoveryItem}>
            <strong>{item.taskKey || item.assignmentId}</strong>
            <small>
              {item.status || 'reported'} · {item.localStage || 'checkpoint'} · {item.recommendedAction || 'monitor'}
            </small>
          </article>
        ))}
      </div>
    </section>
  );
}
