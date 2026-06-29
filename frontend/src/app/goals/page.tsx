'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../utils/api';
import AppShell from '../../components/AppShell';
import styles from './Goals.module.css';
import { Target, Calendar, ArrowRight, MessageSquare, Plus } from 'lucide-react';

export default function GoalsPage() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [deadline, setDeadline] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const { data: goals, refetch } = useQuery({
    queryKey: ['goals-list'],
    queryFn: async () => {
      try {
        return await apiRequest('/api/v1/goals');
      } catch {
        return [
          { 
            id: 'g1', 
            title: 'Launch SaaS MVP', 
            description: 'Deploy fully operational SaaS app to Render and get first 10 beta signups',
            progress: 0.67, 
            deadline: '2026-09-28T00:00:00Z', 
            priority_score: 0.92,
            projects: ['Backend API', 'Frontend Dashboard', 'Stripe Billing']
          },
          { 
            id: 'g2', 
            title: 'Learn Rust Programming', 
            description: 'Build a CLI and a web server in Rust to master memory safety concepts',
            progress: 0.30, 
            deadline: '2026-08-31T00:00:00Z', 
            priority_score: 0.75,
            projects: ['CLI Tool', 'Actix Web API']
          },
          { 
            id: 'g3', 
            title: 'Read 24 books in 2026', 
            description: 'Read biography, tech, history, and fiction books',
            progress: 0.50, 
            deadline: '2026-12-31T00:00:00Z', 
            priority_score: 0.45,
            projects: ['Reading List']
          }
        ];
      }
    }
  });

  const handleCreateGoal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || submitting) return;

    setSubmitting(true);
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
      alert("Error: Failed to create goal. Check backend connectivity.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppShell>
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>Goals & Milestones</h1>
          <button className={styles.btnNew} onClick={() => setIsModalOpen(true)}>
            <Plus size={16} style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'middle' }} />
            New Goal
          </button>
        </div>

        <div className={styles.list}>
          {goals?.map((goal: any, index: number) => {
            const colorMap = ['var(--color-success)', 'var(--color-warning)', 'var(--color-info)'];
            const progressColor = colorMap[index % colorMap.length];
            const isCritical = goal.priority_score > 0.8;
            
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
                    <span style={{ color: progressColor }}>{Math.round(goal.progress * 100)}%</span>
                  </div>
                  <div className={styles.barBg}>
                    <div 
                      className={styles.barFill} 
                      style={{ 
                        width: `${goal.progress * 100}%`,
                        backgroundColor: progressColor,
                        boxShadow: `0 0 8px ${progressColor}50`
                      }} 
                    />
                  </div>
                </div>

                <div className={styles.cardFooter}>
                  <div className={styles.projectsList}>
                    {goal.projects?.map((proj: string) => (
                      <span key={proj} className={styles.projectChip}>{proj}</span>
                    ))}
                  </div>
                  
                  <div className={styles.actions}>
                    <button className={styles.btnAction}>
                      <MessageSquare size={12} style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'middle' }} />
                      Chat
                    </button>
                    <button className={styles.btnAction}>
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
    </AppShell>
  );
}

