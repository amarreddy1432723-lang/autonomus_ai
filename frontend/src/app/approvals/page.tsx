'use client';

import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../utils/api';
import AppShell from '../../components/AppShell';
import styles from './Approvals.module.css';
import { ShieldCheck, Mail, GitCommit, Check } from 'lucide-react';

export default function ApprovalsPage() {
  const queryClient = useQueryClient();

  const { data: approvals = [], isLoading, isError } = useQuery({
    queryKey: ['approvals-list'],
    queryFn: async () => {
      return await apiRequest('/api/v1/approvals?status=pending&page_size=50');
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
    resolveMutation.mutate({ id, status });
  };

  return (
    <AppShell>
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>Pending Approvals</h1>
        </div>

        {isLoading && <div className={styles.emptyState}>Loading approvals...</div>}
        {isError && <div className={styles.emptyState}>Approvals could not be loaded from the backend.</div>}

        {!isLoading && !isError && approvals.length > 0 ? (
          <div className={styles.list}>
            {approvals.map((app: any) => (
              <div key={app.id} className={styles.card}>
                <div className={styles.cardHeader}>
                  <span className={styles.actionType}>
                    {app.action_type === 'send_email' ? <Mail size={16} /> : <GitCommit size={16} />}
                    {app.action_type === 'send_email' ? 'SEND EMAIL' : 'REVIEW ACTION'}
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
          !isLoading && !isError && <div className={styles.emptyState}>
            <Check size={40} color="var(--color-success)" />
            <span className={styles.emptyTitle}>All caught up</span>
            <span>No pending approvals requiring your attention.</span>
          </div>
        )}
      </div>
    </AppShell>
  );
}
