'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../utils/api';
import AppShell from '../../components/AppShell';
import styles from './Tasks.module.css';
import { Cpu, CheckCircle2, Play, ShieldCheck } from 'lucide-react';

export default function TasksPage() {
  const { data: tasks = [], isLoading, isError } = useQuery({
    queryKey: ['tasks-list'],
    queryFn: async () => {
      const response = await apiRequest('/api/v1/tasks?page_size=100');
      if (response && response.results) return response.results;
      return response;
    }
  });

  const columns = [
    { key: 'queued', title: 'Queued', icon: Cpu, iconColor: 'var(--color-text-secondary)' },
    { key: 'in_progress', title: 'In Progress', icon: Play, iconColor: 'var(--color-info)' },
    { key: 'waiting_approval', title: 'Waiting Approval', icon: ShieldCheck, iconColor: 'var(--color-warning)' },
    { key: 'done', title: 'Done', icon: CheckCircle2, iconColor: 'var(--color-success)' }
  ];

  const getPriorityBadgeClass = (score: number) => {
    if (score > 0.9) return styles.badgeCritical;
    if (score > 0.75) return styles.badgeHigh;
    return styles.badgeMed;
  };

  const getPriorityLabel = (score: number) => {
    if (score > 0.9) return 'Critical';
    if (score > 0.75) return 'High';
    return 'Medium';
  };

  return (
    <AppShell>
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>Tasks Kanban Board</h1>
        </div>
        {isLoading && <div className={styles.statePanel}>Loading tasks...</div>}
        {isError && <div className={styles.statePanel}>Tasks could not be loaded from the backend.</div>}

        <div className={styles.board}>
          {columns.map((col) => {
            const Icon = col.icon;
            const columnTasks = tasks?.filter((t: any) => t.status === col.key) || [];
            
            return (
              <div key={col.key} className={styles.column}>
                <div className={styles.columnHeader}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Icon size={16} color={col.iconColor} />
                    <span>{col.title}</span>
                  </div>
                  <span className={styles.columnCount}>{columnTasks.length}</span>
                </div>

                <div className={styles.taskList}>
                  {columnTasks.length === 0 && (
                    <div className={styles.emptyColumn}>No tasks</div>
                  )}
                  {columnTasks.map((task: any) => (
                    <div key={task.id} className={styles.taskCard}>
                      <span className={styles.taskTitle}>{task.title}</span>
                      
                      <div className={styles.taskMeta}>
                        <span className={`${styles.badge} ${getPriorityBadgeClass(task.priority_score)}`}>
                          {getPriorityLabel(task.priority_score)}
                        </span>
                        
                        {task.assigned_agent && (
                          <div className={styles.agentBadge}>
                            <Cpu size={10} />
                            <span>{task.assigned_agent.split(' ')[0]}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
}
