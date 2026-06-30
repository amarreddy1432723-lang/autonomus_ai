'use client';

import React, { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { apiRequest } from '../../utils/api';
import AppShell from '../../components/AppShell';
import styles from './Goals.module.css';
import { Target, Calendar, ArrowRight, MessageSquare, Plus } from 'lucide-react';

export default function GoalsPage() {
  const router = useRouter();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedGoal, setSelectedGoal] = useState<any | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [deadline, setDeadline] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => {
    if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('new') === '1') {
      setIsModalOpen(true);
    }
  }, []);

  const { data: goals, refetch } = useQuery({
    queryKey: ['goals-list'],
    queryFn: async () => {
      return await apiRequest('/api/v1/goals?page_size=50');
    }
  });

  const handleCreateGoal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || submitting) return;

    setSubmitting(true);
    setFormError('');
    try {
      await apiRequest('/api/v1/goals', {
        method: 'POST',
        body: JSON.stringify({
          title,
          description,
          deadline: deadline ? new Date(deadline).toISOString() : undefined
        })
      });
      setIsModalOpen(false);
      setTitle('');
      setDescription('');
      setDeadline('');
      refetch();
    } catch (err) {
      console.error("Failed to create goal:", err);
      setFormError(err instanceof Error ? err.message : 'Failed to create goal.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppShell>
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>Goals & Milestones</h1>
          <button className={styles.btnNew} onClick={() => { setFormError(''); setIsModalOpen(true); }}>
            <Plus size={16} style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'middle' }} />
            New Goal
          </button>
        </div>

        <div className={styles.list}>
          {goals?.length === 0 && (
            <div className={styles.emptyState}>No goals yet. Create one and the planner will generate projects and tasks.</div>
          )}
          {goals?.map((goal: any, index: number) => {
            const colorMap = ['var(--color-success)', 'var(--color-warning)', 'var(--color-info)'];
            const progressColor = colorMap[index % colorMap.length];
            const isCritical = goal.priority_score > 0.8;
            const progress = goal.progress_pct ?? goal.progress ?? 0;
            
            return (
              <div key={goal.id} className={styles.goalCard}>
                <div className={styles.cardHeader}>
                  <div className={styles.cardTitleArea}>
                    <h2 className={styles.cardTitle}>
                      <Target size={18} style={{ color: progressColor }} />
                      {goal.title}
                    </h2>
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginTop: '2px' }}>
                      {goal.description}
                    </span>
                  </div>
                  <div className={styles.priorityBadges}>
                    <span className={`${styles.badge} ${isCritical ? styles.badgeCritical : styles.badgeHigh}`}>
                      Score: {goal.priority_score.toFixed(2)}
                    </span>
                  </div>
                </div>

                {/* Progress bar */}
                <div className={styles.progressSection}>
                  <div className={styles.progressInfo}>
                    <span>Progress</span>
                    <span style={{ color: progressColor }}>{Math.round(progress * 100)}%</span>
                  </div>
                  <div className={styles.barBg}>
                    <div 
                      className={styles.barFill} 
                      style={{ 
                        width: `${progress * 100}%`,
                        backgroundColor: progressColor,
                        boxShadow: `0 0 8px ${progressColor}50`
                      }} 
                    />
                  </div>
                </div>

                <div className={styles.cardFooter}>
                  <div className={styles.projectsList}>
                    {goal.projects?.map((proj: any) => {
                      const label = typeof proj === 'string' ? proj : proj.title;
                      return <span key={typeof proj === 'string' ? proj : proj.id} className={styles.projectChip}>{label}</span>;
                    })}
                  </div>
                  
                  <div className={styles.actions}>
                    <button
                      className={styles.btnAction}
                      onClick={() => router.push(`/chat?goal=${encodeURIComponent(goal.id)}&title=${encodeURIComponent(goal.title)}`)}
                      type="button"
                    >
                      <MessageSquare size={12} style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'middle' }} />
                      Chat
                    </button>
                    <button className={styles.btnAction} onClick={() => setSelectedGoal(goal)} type="button">
                      Details
                      <ArrowRight size={12} style={{ marginLeft: '4px', display: 'inline-block', verticalAlign: 'middle' }} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {isModalOpen && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalContent}>
            <h2 className={styles.modalTitle}>Create New Goal</h2>
            <form onSubmit={handleCreateGoal} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
              {formError && <div className={styles.formError}>{formError}</div>}
              <div className={styles.formGroup}>
                <label htmlFor="goal-title">Goal Title</label>
                <input 
                  id="goal-title"
                  type="text" 
                  placeholder="e.g. Build a mobile app, Learn Kubernetes..." 
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                />
              </div>
              <div className={styles.formGroup}>
                <label htmlFor="goal-desc">Description</label>
                <textarea 
                  id="goal-desc"
                  placeholder="Describe details, success criteria, milestones..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
              <div className={styles.formGroup}>
                <label htmlFor="goal-deadline">Deadline</label>
                <input 
                  id="goal-deadline"
                  type="date"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                />
              </div>
              <div className={styles.modalActions}>
                <button type="button" className={styles.btnCancel} onClick={() => setIsModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className={styles.btnSubmit} disabled={submitting}>
                  {submitting ? 'Creating Plan...' : 'Create & Plan Goal'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {selectedGoal && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalContent}>
            <h2 className={styles.modalTitle}>{selectedGoal.title}</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
              <p>{selectedGoal.description || 'No description saved for this goal.'}</p>
              <p>Status: {selectedGoal.status || 'active'}</p>
              <p>Progress: {Math.round((selectedGoal.progress || 0) * 100)}%</p>
              <p>Plan version: {selectedGoal.plan_version || 1}</p>
              {selectedGoal.category && <p>Category: {selectedGoal.category}</p>}
              {selectedGoal.estimated_hours_total && <p>Estimated effort: {selectedGoal.estimated_hours_total} hours</p>}
              {selectedGoal.deadline && <p>Deadline: {new Date(selectedGoal.deadline).toLocaleDateString()}</p>}
              {selectedGoal.projects?.length > 0 && <p>Projects: {selectedGoal.projects.length}</p>}
              {selectedGoal.tasks?.length > 0 && <p>Tasks: {selectedGoal.tasks.length}</p>}
              {selectedGoal.current_plan?.critical_path?.length > 0 && (
                <p>Critical path: {selectedGoal.current_plan.critical_path.join(' -> ')}</p>
              )}
            </div>
            <div className={styles.modalActions}>
              <button type="button" className={styles.btnCancel} onClick={() => setSelectedGoal(null)}>
                Close
              </button>
              <button
                type="button"
                className={styles.btnSubmit}
                onClick={() => router.push(`/chat?goal=${encodeURIComponent(selectedGoal.id)}&title=${encodeURIComponent(selectedGoal.title)}`)}
              >
                Open Chat
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
