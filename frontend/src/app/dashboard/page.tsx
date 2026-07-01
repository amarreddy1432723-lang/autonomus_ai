'use client';

import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../utils/api';
import AppShell from '../../components/AppShell';
import styles from './Dashboard.module.css';
import { BriefcaseBusiness, ExternalLink, Newspaper, Play, RefreshCw, TrendingUp, ShieldCheck, Cpu } from 'lucide-react';

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const todayLabel = new Intl.DateTimeFormat(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric'
  }).format(new Date());

  const { data: goals = [] } = useQuery({
    queryKey: ['dashboard-goals'],
    queryFn: async () => {
      return await apiRequest('/api/v1/goals?status=active&page_size=5');
    }
  });

  const { data: tasks = [] } = useQuery({
    queryKey: ['dashboard-tasks'],
    queryFn: async () => {
      return await apiRequest('/api/v1/tasks?page_size=8');
    }
  });

  const { data: approvals = [] } = useQuery({
    queryKey: ['dashboard-approvals'],
    queryFn: async () => {
      return await apiRequest('/api/v1/approvals?status=pending&page_size=5');
    }
  });

  const { data: liveNews, refetch: refetchNews, isFetching: newsFetching } = useQuery({
    queryKey: ['live-news', 'ai-agents'],
    queryFn: async () => {
      try {
        return await apiRequest('/api/v1/news/live?query=AI%20agents%20OR%20autonomous%20AI&limit=5');
      } catch (error) {
        return {
          query: 'AI agents OR autonomous AI',
          items: [
            {
              title: 'Live news service needs attention',
              source: 'Agent service',
              published_at: new Date().toISOString(),
              link: '',
              snippet: error instanceof Error ? error.message : 'Retry once network access is available.'
            }
          ]
        };
      }
    },
    staleTime: 5 * 60 * 1000,
  });

  const { data: liveJobs, refetch: refetchJobs, isFetching: jobsFetching } = useQuery({
    queryKey: ['live-jobs', 'ai-engineer-remote'],
    queryFn: async () => {
      try {
        return await apiRequest('/api/v1/jobs/live?query=AI%20engineer%20remote&limit=5');
      } catch (error) {
        return {
          query: 'AI engineer remote',
          items: [
            {
              title: 'Job notifications need attention',
              company: 'Agent service',
              location: 'Remote',
              apply_url: '',
              source: 'Job service',
              published_at: new Date().toISOString(),
              tags: [error instanceof Error ? error.message : 'Retry once the job feed is available.']
            }
          ]
        };
      }
    },
    staleTime: 5 * 60 * 1000,
  });

  const runTasksMutation = useMutation({
    mutationFn: async () => apiRequest('/api/v1/tasks/run', { method: 'POST' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['dashboard-goals'] });
      await queryClient.invalidateQueries({ queryKey: ['dashboard-tasks'] });
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

  const prioritizedTasks = [...tasks]
    .filter((task: any) => !['done', 'completed'].includes(task.status))
    .sort((a: any, b: any) => (b.priority_score || 0) - (a.priority_score || 0))
    .slice(0, 4);
  const completedThisWeek = tasks.filter((task: any) => ['done', 'completed'].includes(task.status)).length;
  const averageProgress = goals.length
    ? Math.round(goals.reduce((sum: number, goal: any) => sum + ((goal.progress_pct ?? goal.progress ?? 0) * 100), 0) / goals.length)
    : 0;

  return (
    <AppShell>
      <div className={styles.header}>
        <h1 className={styles.title}>Good morning, Amar</h1>
        <p className={styles.subtitle}>{todayLabel} · Your AI workspace is synced with the current backend state.</p>
      </div>

      {/* QUICK STATS ROW */}
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Tasks Completed</span>
          <span className={styles.statValue}>{completedThisWeek}</span>
          <span className={styles.statDesc}>Done in the current task view</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Active Goals</span>
          <span className={styles.statValue}>{goals.length}</span>
          <span className={styles.statDesc}>Active goals in focus</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Average Progress</span>
          <span className={styles.statValue}>{averageProgress}%</span>
          <span className={styles.statDesc}>Across all active goals</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>AI Cost Today</span>
          <span className={styles.statValue}>Live</span>
          <span className={styles.statDesc}>Tracked by backend executions</span>
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
              {prioritizedTasks.length === 0 && (
                <div className={styles.emptyInline}>No open tasks found. Create a goal to generate a plan.</div>
              )}
              {prioritizedTasks.map((task: any) => (
                <div key={task.id} className={styles.focusItem}>
                  <div className={styles.focusInfo}>
                    <span className={styles.focusTitle}>
                      <span className={`${styles.priorityDot} ${(task.priority_score || 0) > 0.8 ? styles.priorityDotCritical : styles.priorityDotHigh}`} />
                      {task.title}
                    </span>
                    <div className={styles.focusMeta}>
                      <span>{task.status}</span>
                      <span>·</span>
                      <span>{task.est_hours_pert || task.pert_estimate || 0}h est</span>
                      <span>·</span>
                      <span>{task.assigned_agent || 'Agent'}</span>
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
              {approvals.length === 0 && (
                <div className={styles.emptyInline}>No pending approvals.</div>
              )}
              {approvals.map((app: any) => (
                <div key={app.id} className={styles.approvalItem}>
                  <div className={styles.approvalDetails}>
                    <span className={styles.approvalTitle}>
                      {app.action_type === 'send_email' ? 'Send email' : 'Review action'}
                    </span>
                    <span className={styles.approvalMeta}>
                      {app.action_type === 'send_email' 
                        ? `To: ${app.payload?.to || 'unknown'} · Subject: ${app.payload?.subject || 'No subject'}`
                        : app.action_description || app.payload?.message || 'Manual approval required'}
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

          <div className={styles.liveGrid}>
            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <div className={styles.cardTitle}>
                  <Newspaper size={16} color="var(--color-info)" />
                  <span>Live AI News</span>
                </div>
                <button className={styles.iconButton} onClick={() => refetchNews()} type="button" title="Refresh live news">
                  <RefreshCw size={14} className={newsFetching ? styles.spin : ''} />
                </button>
              </div>

              <div className={styles.newsList}>
                {liveNews?.items?.map((item: any) => (
                  <a
                    className={styles.newsItem}
                    href={item.link || undefined}
                    target="_blank"
                    rel="noreferrer"
                    key={`${item.title}-${item.source}`}
                  >
                    <span className={styles.newsTitle}>{item.title}</span>
                    <span className={styles.newsMeta}>
                      {item.source} · {item.published_at ? new Date(item.published_at).toLocaleString() : 'recent'}
                    </span>
                  </a>
                ))}
              </div>
            </div>

            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <div className={styles.cardTitle}>
                  <BriefcaseBusiness size={16} color="var(--color-success)" />
                  <span>New Job Alerts</span>
                </div>
                <button className={styles.iconButton} onClick={() => refetchJobs()} type="button" title="Refresh job alerts">
                  <RefreshCw size={14} className={jobsFetching ? styles.spin : ''} />
                </button>
              </div>

              <div className={styles.newsList}>
                {liveJobs?.items?.map((job: any) => (
                  <div className={styles.jobItem} key={`${job.title}-${job.company}-${job.apply_url}`}>
                    <div className={styles.jobBody}>
                      <span className={styles.newsTitle}>{job.title}</span>
                      <span className={styles.newsMeta}>
                        {job.company} · {job.location} · {job.published_at ? new Date(job.published_at).toLocaleDateString() : 'recent'}
                      </span>
                      {job.tags?.length > 0 && (
                        <div className={styles.tagRow}>
                          {job.tags.slice(0, 3).map((tag: string) => (
                            <span className={styles.jobTag} key={tag}>{tag}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    {job.apply_url ? (
                      <a className={styles.applyLink} href={job.apply_url} target="_blank" rel="noreferrer">
                        <ExternalLink size={12} />
                        Apply
                      </a>
                    ) : (
                      <span className={styles.disabledApply}>Unavailable</span>
                    )}
                  </div>
                ))}
              </div>
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
              {goals.length === 0 && (
                <div className={styles.emptyInline}>No active goals yet.</div>
              )}
              {goals.map((goal: any, index: number) => {
                const colorMap = ['var(--color-success)', 'var(--color-warning)', 'var(--color-info)'];
                const progressColor = colorMap[index % colorMap.length];
                const progress = goal.progress_pct ?? goal.progress ?? 0;
                return (
                  <div key={goal.id} className={styles.goalItem}>
                    <div className={styles.goalInfo}>
                      <span>{goal.title}</span>
                      <span style={{ color: progressColor }}>{Math.round(progress * 100)}%</span>
                    </div>
                    <div className={styles.progressBarContainer}>
                      <div 
                        className={styles.progressBar} 
                        style={{ 
                          width: `${progress * 100}%`,
                          backgroundColor: progressColor,
                          boxShadow: `0 0 10px ${progressColor}50`
                        }} 
                      />
                    </div>
                    <span className={styles.goalMeta}>{goal.deadline ? new Date(goal.deadline).toLocaleDateString() : 'No deadline'}</span>
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
