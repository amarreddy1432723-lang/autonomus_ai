'use client';

import { Check, CircleDot, Eye, FilePenLine, Rocket, Search, Sparkles, X } from 'lucide-react';
import styles from './Workspace.module.css';

export type ActivityEvent = {
  id: string;
  kind: 'start' | 'read' | 'code' | 'design' | 'deploy' | 'research' | 'edit' | 'done' | 'error';
  message: string;
  detail?: string;
  diff?: string;
};

type Props = {
  events: ActivityEvent[];
  hasPatch: boolean;
  canApply: boolean;
  onApply: () => void;
  onReject: () => void;
  canRunCommand: boolean;
  onRunCommand: (command: string) => void;
};

function Icon({ kind }: { kind: ActivityEvent['kind'] }) {
  if (kind === 'research') return <Search size={15} />;
  if (kind === 'design') return <Sparkles size={15} />;
  if (kind === 'deploy') return <Rocket size={15} />;
  if (kind === 'edit' || kind === 'code') return <FilePenLine size={15} />;
  if (kind === 'done') return <Check size={15} />;
  if (kind === 'error') return <X size={15} />;
  return <CircleDot size={15} />;
}

function Diff({ diff }: { diff: string }) {
  return (
    <pre className={styles.diffBox}>
      {diff.split('\n').map((line, index) => (
        <span
          key={`${line}-${index}`}
          className={line.startsWith('+') ? styles.added : line.startsWith('-') ? styles.removed : undefined}
        >
          {line}
          {'\n'}
        </span>
      ))}
    </pre>
  );
}

const commands = [
  { label: 'Build', command: 'npm run build' },
  { label: 'Test', command: 'npm test' },
  { label: 'Lint', command: 'npm run lint' },
  { label: 'Typecheck', command: 'npm run typecheck' },
];

export default function ActivityPanel({ events, hasPatch, canApply, onApply, onReject, canRunCommand, onRunCommand }: Props) {
  return (
    <aside className={styles.activity}>
      <div className={styles.panelHeader}>
        <span>Activity / Changes</span>
        <Eye size={15} />
      </div>
      <div className={styles.activityList}>
        {events.map((event) => (
          <div className={styles.activityItem} key={event.id}>
            <div className={styles.activityTitle}>
              <Icon kind={event.kind} />
              <span>{event.message}</span>
            </div>
            {event.detail && <div className={styles.activityDetail}>{event.detail}</div>}
            {event.diff && <Diff diff={event.diff} />}
          </div>
        ))}
        {events.length === 0 && (
          <div className={styles.meta}>
            Activity appears here as NEXUS reads files, researches, designs, edits, and prepares deployment steps.
          </div>
        )}
      </div>
      <div className={styles.activityFooter}>
        <div className={styles.commandGrid}>
          {commands.map((item) => (
            <button key={item.command} className={styles.commandButton} type="button" onClick={() => onRunCommand(item.command)} disabled={!canRunCommand}>
              {item.label}
            </button>
          ))}
        </div>
        <button className={styles.approveButton} type="button" onClick={onApply} disabled={!canApply}>
          <Check size={15} /> Approve all changes
        </button>
        <button className={styles.rejectButton} type="button" onClick={onReject} disabled={!hasPatch}>
          <X size={15} /> Reject changes
        </button>
      </div>
    </aside>
  );
}
