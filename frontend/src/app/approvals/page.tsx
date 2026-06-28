'use client';

import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../utils/api';
import AppShell from '../../components/AppShell';
import styles from './Approvals.module.css';
import { ShieldCheck, Mail, GitCommit, Check } from 'lucide-react';

export default function ApprovalsPage() {
  const queryClient = useQueryClient();

  const { data: approvals, isLoading } = useQuery({
    queryKey: ['approvals-list'],
    queryFn: async () => {
      try {
        return await apiRequest('/api/v1/approvals');
      } catch {
        return [
          { 
            id: 'a1', 
            action_type: 'send_email', 
            payload: { 
              to: 'sarah.chen@vcfirm.com', 
              subject: 'Following up on our conversation',
              body: 'Hi Sarah,\n\nHope you had a great week. I wanted to follow up on our meeting from June 20. We have successfully completed database schema migrations for the SaaS MVP project.'
            }, 
            status: 'pending', 
            why: 'User requested to draft a follow-up email to Sarah Chen. Since sending emails is an external, irreversible action, it was classified as HIGH RISK and held for approval.',
            requested_at: '2 min ago' 
          },
          { 
            id: 'a2', 
            action_type: 'git_commit', 
            payload: { 
              message: 'Add JWT authorization middleware with unit tests passing',
              branch: 'feature/auth'
            }, 
            status: 'pending', 
            why: 'Coding Agent finished task T2 and requested to commit code changes to a shared branch. Held for approval according to autonomy level Settings.',
            requested_at: '8 min ago' 
          }
        ];
      }
    }
  });

  const resolveMutation = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: 'approved' | 'rejected' }) => {
      return await apiRequest(`/api/v1/approvals/${id}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ status })
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals-list'] });
    }
  });

  const handleResolve = (id: string, status: 'approved' | 'rejected') => {
    // If backend is running, execute mutation, otherwise just alert for demo
    resolveMutation.mutate({ id, status }, {
      onError: () => {
        alert(`Simulated resolution: ${status} approval ${id}`);
      }
    });
  };

  return (
    <AppShell>
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>Pending Approvals</h1>
        </div>

        {approvals && approvals.length > 0 ? (
          <div className={styles.list}>
            {approvals.map((app: any) => (
              <div key={app.id} className={styles.card}>
                <div className={styles.cardHeader}>
                  <span className={styles.actionType}>
                    {app.action_type === 'send_email' ? <Mail size={16} /> : <GitCommit size={16} />}
                    {app.action_type === 'send_email' ? '📧 SEND EMAIL' : '💻 GIT COMMIT & PUSH'}
                  </span>
                  <span className={styles.badge}>HIGH RISK</span>
                </div>

                <div className={styles.why}>
                  <strong>Reasoning:</strong> {app.why || 'Held for manual policy verification.'}
                </div>

                <div className={styles.payloadBox}>
                  {JSON.stringify(app.payload, null, 2)}
                </div>

                <div className={styles.footer}>
                  <span className={styles.time}>Requested {app.requested_at}</span>
                  <div className={styles.actions}>
                    <button 
                      className={styles.btnApprove}
                      onClick={() => handleResolve(app.id, 'approved')}
                    >
                      Approve
                    </button>
                    <button 
                      className={styles.btnReject}
                      onClick={() => handleResolve(app.id, 'rejected')}
                    >
                      Reject
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className={styles.emptyState}>
            <Check size={40} color="var(--color-success)" />
            <span className={styles.emptyTitle}>All caught up!</span>
            <span>No pending approvals requiring your attention.</span>
          </div>
        )}
      </div>
    </AppShell>
  );
}
