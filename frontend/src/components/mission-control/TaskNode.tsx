import styles from './MissionControlProduct.module.css';
import { taskStatusLabel } from './statusCopy';
import type { MissionControlTask } from './types';

export function TaskNode({ task }: { task: MissionControlTask }) {
  return (
    <article className={styles.taskNode} data-state={task.status}>
      <span className={styles.taskDot} aria-hidden="true" />
      <div>
        <strong>{task.title || task.taskKey}</strong>
        <small>{task.blockedReason || task.taskKey}</small>
      </div>
      <span className={styles.taskBadge}>{taskStatusLabel(task.status)}</span>
    </article>
  );
}
