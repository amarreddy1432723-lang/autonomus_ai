import styles from './MissionControlProduct.module.css';
import type { MissionControlMetricsData } from './types';

export function MissionProgress({ metrics }: { metrics: MissionControlMetricsData }) {
  const total = Math.max(0, metrics.taskCount || 0);
  const completed = Math.max(0, metrics.completedTasks || 0);
  const running = Math.max(0, metrics.runningTasks || 0);
  const blocked = Math.max(0, metrics.blockedTasks || 0);

  return (
    <section className={styles.panel} aria-label="Mission progress">
      <header>
        <div>
          <h3>Progress</h3>
          <p>How the mission is moving through the execution runtime.</p>
        </div>
      </header>
      <div className={styles.metricGrid}>
        <article className={styles.metric}>
          <b>{completed}</b>
          <strong>Completed</strong>
          <small>of {total} total tasks</small>
        </article>
        <article className={styles.metric}>
          <b>{running}</b>
          <strong>Running</strong>
          <small>currently claimed</small>
        </article>
        <article className={styles.metric}>
          <b>{blocked}</b>
          <strong>Blocked</strong>
          <small>waiting on review or dependency</small>
        </article>
        <article className={styles.metric}>
          <b>{metrics.activeReservations || 0}</b>
          <strong>Locks</strong>
          <small>protected repository paths</small>
        </article>
      </div>
    </section>
  );
}
