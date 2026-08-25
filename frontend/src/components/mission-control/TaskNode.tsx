import styles from './MissionControlProduct.module.css';
import { taskStatusLabel } from './statusCopy';
import type { MissionControlTask } from './types';

export function TaskNode({
  task,
  selected = false,
  onSelect,
}: {
  task: MissionControlTask;
  selected?: boolean;
  onSelect?: () => void;
}) {
  return (
    <button type="button" className={styles.taskNode} data-state={task.status} data-selected={selected} onClick={onSelect}>
      <span className={styles.taskDot} aria-hidden="true" />
      <div>
        <strong>{task.title || task.taskKey}</strong>
        <small>{task.blockedReason || task.taskKey}</small>
      </div>
      <span className={styles.taskBadge}>{taskStatusLabel(task.status)}</span>
    </button>
  );
}
