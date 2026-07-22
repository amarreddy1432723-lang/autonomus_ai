import styles from './MissionControlProduct.module.css';
import { heartbeatLabel } from './statusCopy';
import type { MissionControlWorker } from './types';

function initials(role: string) {
  return role
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'AI';
}

export function WorkerCard({ worker }: { worker: MissionControlWorker }) {
  const heartbeat = heartbeatLabel(worker.heartbeatAgeSeconds);
  const task = worker.currentTaskTitle || worker.currentTaskKey || 'Waiting for assignment';

  return (
    <article className={styles.workerCard}>
      <span className={styles.avatar}>{initials(worker.role)}</span>
      <div>
        <strong>{worker.role}</strong>
        <small>{task}</small>
      </div>
      <span className={styles.miniPill} data-state={heartbeat}>
        {heartbeat}
      </span>
    </article>
  );
}
