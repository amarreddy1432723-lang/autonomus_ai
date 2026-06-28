'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../utils/api';
import AppShell from '../../components/AppShell';
import styles from './Tasks.module.css';
import { Cpu, CheckCircle2, AlertTriangle, ShieldCheck } from 'lucide-react';

export default function TasksPage() {
  const { data: tasks } = useQuery({
    queryKey: ['tasks-list'],
    queryFn: async () => {
      try {
        const response = await apiRequest('/api/v1/tasks');
        // If the backend returns a dict, extract tasks
        if (response && response.results) return response.results;
        return response;
      } catch {
        return [
          { id: 't1', title: 'T1: Create database migrations & models', status: 'done', priority_score: 0.95, assigned_agent: 'Coding Agent' },
          { id: 't2', title: 'T2: Implement Auth Service JWT verification', status: 'in_progress', priority_score: 0.92, assigned_agent: 'Coding Agent' },
          { id: 't3', title: 'T3: Design User Profile API route handlers', status: 'queued', priority_score: 0.85, assigned_agent: 'Coding Agent' },
          { id: 't4', title: 'T4: Setup Stripe Billing integration', status: 'queued', priority_score: 0.78, assigned_agent: 'Coding Agent' },
          { id: 't5', title: 'T5: Setup Render hosting deployment pipeline', status: 'queued', priority_score: 0.65, assigned_agent: 'Coding Agent' },
          { id: 't6', title: 'T6: Send follow-up email to Sarah Chen', status: 'waiting_approval', priority_score: 0.72, assigned_agent: 'Research Agent' },
          { id: 't7', title: 'T7: Write complete Integration Test Suite', status: 'queued', priority_score: 0.55, assigned_agent: 'Exec Agent' }
        ];
      }
    }
  });

  const columns = [
    { key: 'queued', title: 'Queued', icon: Cpu, iconColor: 'var(--color-text-secondary)' },
    { key: 'in_progress', title: 'In Progress', icon: PlayIcon, iconColor: 'var(--color-info)' },
    { key: 'waiting_approval', title: 'Waiting Approval', icon: ShieldCheck, iconColor: 'var(--color-warning)' },
    { key: 'done', title: 'Done', icon: CheckCircle2, iconColor: 'var(--color-success)' }
  ];

  function PlayIcon(props: any) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" {...props}>
        <polygon points="5 3 19 12 5 21 5 3" />
      </svg>
    );
  }

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
