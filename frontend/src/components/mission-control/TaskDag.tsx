import styles from './MissionControlProduct.module.css';
import type { MissionControlEdge, MissionControlTask } from './types';
import { TaskNode } from './TaskNode';

const FALLBACK_TASKS: MissionControlTask[] = [
  { taskId: 'mission-intake', taskKey: 'mission.intake', title: 'Mission intake', status: 'completed' },
  { taskId: 'repo-analysis', taskKey: 'repository.analysis', title: 'Repository analysis', status: 'running' },
  { taskId: 'verification', taskKey: 'verification.evidence', title: 'Evidence verification', status: 'ready' },
];

export function TaskDag({ tasks, edges }: { tasks: MissionControlTask[]; edges: MissionControlEdge[] }) {
  const visibleTasks = tasks.length > 0 ? tasks : FALLBACK_TASKS;

  return (
    <section className={styles.panel} aria-label="Task dependency graph">
      <header>
        <div>
          <h3>Execution Graph</h3>
          <p>Task order, blockers, and dependency flow.</p>
        </div>
        <span className={styles.taskBadge}>{edges.length} links</span>
      </header>
      <div className={styles.taskList}>
        {visibleTasks.map((task) => (
          <TaskNode key={task.taskId || task.taskKey} task={task} />
        ))}
      </div>
    </section>
  );
}
