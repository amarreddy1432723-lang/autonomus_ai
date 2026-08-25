import { CheckCircle2, Clock3, XCircle } from 'lucide-react';
import styles from './MissionControlProduct.module.css';
import type { MissionControlVerificationStep } from './types';

const iconFor = (status: string) => {
  if (status === 'passed') return <CheckCircle2 size={14} />;
  if (status === 'failed' || status === 'blocked') return <XCircle size={14} />;
  return <Clock3 size={14} />;
};

export function VerificationPanel({ checks }: { checks: MissionControlVerificationStep[] }) {
  const visibleChecks = checks.length
    ? checks
    : [
        { id: 'typecheck', label: 'Type check', status: 'not_run', summary: 'Awaiting mission evidence.' },
        { id: 'lint', label: 'Lint', status: 'not_run', summary: 'Awaiting mission evidence.' },
        { id: 'tests', label: 'Tests', status: 'not_run', summary: 'Awaiting mission evidence.' },
        { id: 'build', label: 'Build', status: 'not_run', summary: 'Awaiting mission evidence.' },
      ];

  return (
    <section className={styles.panel} aria-label="Verification panel">
      <header>
        <div>
          <h3>Verification</h3>
          <p>Checks must pass before PR, deployment, or mission completion.</p>
        </div>
        <span className={styles.taskBadge}>{visibleChecks.filter((check) => check.status === 'passed').length}/{visibleChecks.length} passed</span>
      </header>
      <div className={styles.verifyList}>
        {visibleChecks.map((check) => (
          <article key={check.id} data-state={check.status}>
            <span>{iconFor(check.status)}</span>
            <div>
              <strong>{check.label}</strong>
              <small>{check.command || check.summary || 'No command output recorded yet.'}</small>
            </div>
            <b>{check.status.replace(/_/g, ' ')}</b>
          </article>
        ))}
      </div>
    </section>
  );
}
