'use client';

import { AlertCircle, AlertTriangle, Info, XCircle } from 'lucide-react';
import { useMemo, useState } from 'react';
import styles from './Workspace.module.css';
import type { WorkspaceDiagnostic } from './EditorPanel';

type Props = {
  diagnostics: WorkspaceDiagnostic[];
  activeFile?: string;
  onOpenDiagnostic?: (diagnostic: WorkspaceDiagnostic) => void;
};

function severityIcon(severity?: string) {
  const value = String(severity || 'error').toLowerCase();
  if (value.includes('warn')) return <AlertTriangle size={13} />;
  if (value.includes('info')) return <Info size={13} />;
  return <XCircle size={13} />;
}

function severityLabel(severity?: string) {
  const value = String(severity || 'error').toLowerCase();
  if (value.includes('warn')) return 'warning';
  if (value.includes('info')) return 'info';
  return 'error';
}

function basename(file?: string) {
  if (!file) return 'Current file';
  return file.replace(/\\/g, '/').split('/').filter(Boolean).pop() || file;
}

export default function ProblemsPanel({ diagnostics, activeFile, onOpenDiagnostic }: Props) {
  const [filter, setFilter] = useState<'all' | 'error' | 'warning' | 'info'>('all');
  const active = (activeFile || '').replace(/\\/g, '/').toLowerCase();
  const counts = useMemo(() => ({
    error: diagnostics.filter((item) => severityLabel(item.severity) === 'error').length,
    warning: diagnostics.filter((item) => severityLabel(item.severity) === 'warning').length,
    info: diagnostics.filter((item) => severityLabel(item.severity) === 'info').length,
  }), [diagnostics]);
  const sorted = diagnostics.filter((item) => filter === 'all' || severityLabel(item.severity) === filter).sort((a, b) => {
    const fileA = String(a.file || '');
    const fileB = String(b.file || '');
    if (fileA !== fileB) return fileA.localeCompare(fileB);
    return Number(a.line || 0) - Number(b.line || 0);
  });

  return (
    <div className={styles.problemsPanel}>
      <div className={styles.problemsHeader}>
        <span><AlertCircle size={13} /> Problems</span>
        <em>{counts.error} errors / {diagnostics.length} total</em>
      </div>
      <div className={styles.problemsFilters}>
        {[
          ['all', `All ${diagnostics.length}`],
          ['error', `Errors ${counts.error}`],
          ['warning', `Warnings ${counts.warning}`],
          ['info', `Info ${counts.info}`],
        ].map(([value, label]) => (
          <button
            key={value}
            type="button"
            data-active={filter === value ? 'true' : 'false'}
            onClick={() => setFilter(value as typeof filter)}
          >
            {label}
          </button>
        ))}
      </div>
      {sorted.length ? (
        <div className={styles.problemsList}>
          {sorted.slice(0, 80).map((item, index) => {
            const file = String(item.file || '');
            const normalized = file.replace(/\\/g, '/').toLowerCase();
            const isActive = !file || active.endsWith(normalized) || normalized.endsWith(active) || active.endsWith(basename(file).toLowerCase());
            const severity = severityLabel(item.severity);
            return (
              <button
                key={`${file}-${item.line || 0}-${item.column || 0}-${index}`}
                className={styles.problemRow}
                data-severity={severity}
                data-active={isActive ? 'true' : 'false'}
                type="button"
                onClick={() => onOpenDiagnostic?.(item)}
                title={item.message || 'Workspace diagnostic'}
              >
                {severityIcon(item.severity)}
                <span>{item.message || 'Workspace diagnostic'}</span>
                <em>{basename(file)}:{item.line || 1}:{item.column || 1}</em>
              </button>
            );
          })}
        </div>
      ) : (
        <div className={styles.problemsEmpty}>No diagnostics for this workspace.</div>
      )}
    </div>
  );
}
