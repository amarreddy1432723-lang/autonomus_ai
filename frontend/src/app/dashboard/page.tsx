'use client';

import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../utils/api';
import AppShell from '../../components/AppShell';
import styles from './Dashboard.module.css';
import { Play, TrendingUp, ShieldCheck, Cpu } from 'lucide-react';

export default function DashboardPage() {
  const queryClient = useQueryClient();

  // Query active goals
  const { data: goals } = useQuery({
    queryKey: ['dashboard-goals'],
    queryFn: async () => {
      try {
        return await apiRequest('/api/v1/goals');
      } catch {
        return [
          { id: 'g1', title: 'Launch SaaS MVP', progress: 0.67, deadline: 'Sep 28 · 43 days left', status: 'active' },
          { id: 'g2', title: 'Learn Rust Programming', progress: 0.30, deadline: 'Aug 31 · 64 days left', status: 'active' },
          { id: 'g3', title: 'Read 24 books in 2026', progress: 0.50, deadline: 'On track', status: 'active' }
        ];
      }
    }
  });

  // Query pending approvals
  const { data: approvals } = useQuery({
    queryKey: ['dashboard-approvals'],
    queryFn: async () => {
      try {
        return await apiRequest('/api/v1/approvals');
      } catch {
        return [
          { id: 'a1', action_type: 'send_email', payload: { to: 'sarah.chen@vcfirm.com', subject: 'Following up...' }, status: 'pending', requested_at: '2 min ago' },
          { id: 'a2', action_type: 'git_commit', payload: { message: 'Add JWT authorization middleware' }, status: 'pending', requested_at: '8 min ago' }
        ];
      }
    }
  });

  const runTasksMutation = useMutation({
    mutationFn: async () => apiRequest('/api/v1/tasks/run', { method: 'POST' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['dashboard-goals'] });
      await queryClient.invalidateQueries({ queryKey: ['dashboard-approvals'] });
    }
  });

  const resolveApprovalMutation = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: 'approved' | 'rejected' }) => {
      return apiRequest(`/api/v1/approvals/${id}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ status })
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['dashboard-approvals'] });
    }
  });

  const prioritizedTasks = [
    { id: 't1', title: 'T2: Implement Auth Service (JWT + OAuth)', goal: 'Launch SaaS MVP', est: '8h', agent: 'Coding Agent', priority: 'Critical Path', priorityScore: 0.92 },
    { id: 't2', title: 'T4: Setup Stripe Billing integration', goal: 'Launch SaaS MVP', est: '8h', agent: 'Coding Agent', priority: 'High Priority', priorityScore: 0.78 },
    { id: 't3', title: 'T7: Write Integration Test Suite', goal: 'Launch SaaS MVP', est: '6h', agent: 'Exec Agent', priority: 'Medium Priority', priorityScore: 0.55 }
  ];

  return (
    <AppShell>
      <div className={styles.header}>
        <h1 className={styles.title}>Good Morning, Amar ☀️</h1>
        <p className={styles.subtitle}>Saturday, June 28 · Here's what your AI has planned for you today</p>
      </div>

      {/* QUICK STATS ROW */}
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Tasks Completed</span>
          <span className={styles.statValue}>12 done</span>
          <span className={styles.statDesc}>This week (+4 vs last week)</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Memories Stored</span>
          <span className={styles.statValue}>2,847</span>
          <span className={styles.statDesc}>Semantic contexts cached</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Average Progress</span>
          <span className={styles.statValue}>67%</span>
          <span className={styles.statDesc}>Across all active goals</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>AI Cost Today</span>
          <span className={styles.statValue}>$1.24</span>
          <span className={styles.statDesc}>Tokens and compute spent</span>
        </div>
      </div>

      {/* DASHBOARD GRID */}
      <div className={styles.grid}>
        {/* LEFT COLUMN: Focus Area & Approvals */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* TODAY'S FOCUS */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <div className={styles.cardTitle}>
                <TrendingUp size={16} color="var(--color-accent-primary)" />
                <span>Today's prioritized tasks</span>
              </div>
              <span className={styles.badge}>{prioritizedTasks.length} prioritized</span>
            </div>
            
            <div className={styles.focusList}>
              {prioritizedTasks.map((task) => (
                <div key={task.id} className={styles.focusItem}>
                  <div className={styles.focusInfo}>
                    <span className={styles.focusTitle}>
                      <span className={`${styles.priorityDot} ${task.priorityScore > 0.8 ? styles.priorityDotCritical : styles.priorityDotHigh}`} />
                      {task.title}
                    </span>
                    <div className={styles.focusMeta}>
                      <span>{task.goal}</span>
                      <span>·</span>
                      <span>{task.est} est</span>
                      <span>·</span>
                      <span>{task.agent}</span>
                    </div>
                  </div>
                  <button
                    className={styles.focusAction}
                    onClick={() => runTasksMutation.mutate()}
                    type="button"
                  >
                    <Play size={10} style={{ marginRight: '4px', fill: 'var(--color-text-primary)' }} />
                    Run
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* PENDING APPROVALS */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <div className={styles.cardTitle}>
                <ShieldCheck size={16} color="var(--color-warning)" />
                <span>Pending Approvals</span>
              </div>
              <span className={`${styles.badge} ${styles.badgeUrgent}`}>{approvals?.length || 0} urgent</span>
            </div>

            <div className={styles.approvalsList}>
              {approvals?.map((app: any) => (
                <div key={app.id} className={styles.approvalItem}>
                  <div className={styles.approvalDetails}>
                    <span className={styles.approvalTitle}>
                      {app.action_type === 'send_email' ? '📧 Send email' : '💻 Git commit push'}
                    </span>
                    <span className={styles.approvalMeta}>
                      {app.action_type === 'send_email' 
                        ? `To: ${app.payload.to} · Subject: ${app.payload.subject}`
                        : `Commit msg: ${app.payload.message}`}
                    </span>
                  </div>
                  <div className={styles.approvalActions}>
                    <button
                      className={styles.btnApprove}
                      onClick={() => resolveApprovalMutation.mutate({ id: app.id, status: 'approved' })}
                      type="button"
                    >
                      Approve
                    </button>
                    <button
                      className={styles.btnReject}
                      onClick={() => resolveApprovalMutation.mutate({ id: app.id, status: 'rejected' })}
                      type="button"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Goals & AI Stats */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* ACTIVE GOALS */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <div className={styles.cardTitle}>
                <Cpu size={16} color="var(--color-accent-secondary)" />
                <span>Active Goals</span>
              </div>
            </div>

            <div className={styles.goalList}>
              {goals?.map((goal: any, index: number) => {
                const colorMap = ['var(--color-success)', 'var(--color-warning)', 'var(--color-info)'];
                const progressColor = colorMap[index % colorMap.length];
                return (
                  <div key={goal.id} className={styles.goalItem}>
                    <div className={styles.goalInfo}>
                      <span>{goal.title}</span>
                      <span style={{ color: progressColor }}>{Math.round(goal.progress * 100)}%</span>
                    </div>
                    <div className={styles.progressBarContainer}>
                      <div 
                        className={styles.progressBar} 
                        style={{ 
                          width: `${goal.progress * 100}%`,
                          backgroundColor: progressColor,
                          boxShadow: `0 0 10px ${progressColor}50`
                        }} 
                      />
                    </div>
                    <span className={styles.goalMeta}>{goal.deadline}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
