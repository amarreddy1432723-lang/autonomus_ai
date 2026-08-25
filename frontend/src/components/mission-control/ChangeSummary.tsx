import { CheckCircle2, Filter, RotateCcw, Search, XCircle } from 'lucide-react';
import { useMemo, useState } from 'react';
import styles from './MissionControlProduct.module.css';
import type { MissionControlChangeFile, MissionControlChangeSet } from './types';

function totals(changeSet: MissionControlChangeSet) {
  return changeSet.files.reduce(
    (acc, file) => ({
      additions: acc.additions + (file.additions || 0),
      deletions: acc.deletions + (file.deletions || 0),
      review: acc.review + (file.reviewRequired ? 1 : 0),
    }),
    { additions: 0, deletions: 0, review: 0 },
  );
}

export function ChangeSummary({
  changeSet,
  selectedPath,
  onSelectFile,
  onApproveAll,
  onRejectAll,
  onRollback,
}: {
  changeSet: MissionControlChangeSet;
  selectedPath?: string;
  onSelectFile?: (file: MissionControlChangeFile) => void;
  onApproveAll?: () => void;
  onRejectAll?: () => void;
  onRollback?: () => void;
}) {
  const [query, setQuery] = useState('');
  const [operationFilter, setOperationFilter] = useState('all');
  const [riskFilter, setRiskFilter] = useState('all');
  const summary = totals(changeSet);
  const hasChanges = changeSet.files.length > 0;
  const operations = useMemo(() => {
    const values = Array.from(new Set(changeSet.files.map((file) => file.operation || 'modify')));
    return ['all', ...values];
  }, [changeSet.files]);
  const filteredFiles = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return changeSet.files.filter((file) => {
      const matchesQuery = !normalizedQuery || file.path.toLowerCase().includes(normalizedQuery);
      const matchesOperation = operationFilter === 'all' || file.operation === operationFilter;
      const matchesRisk = riskFilter === 'all' || (riskFilter === 'review' ? file.reviewRequired : (file.risk || 'low') === riskFilter);
      return matchesQuery && matchesOperation && matchesRisk;
    });
  }, [changeSet.files, operationFilter, query, riskFilter]);

  return (
    <section className={styles.panel} aria-label="Change review">
      <header>
        <div>
          <h3>Change Review</h3>
          <p>{hasChanges ? changeSet.summary || 'Generated repository changes are ready for inspection.' : 'No change set has been recorded for this mission yet.'}</p>
        </div>
        <span className={styles.taskBadge}>{changeSet.reviewState.replace(/_/g, ' ')}</span>
      </header>
      <div className={styles.changeStats}>
        <span><b>{changeSet.files.length}</b> files</span>
        <span data-tone="good"><b>+{summary.additions}</b> additions</span>
        <span data-tone="bad"><b>-{summary.deletions}</b> deletions</span>
        <span data-tone={summary.review ? 'warn' : 'good'}><b>{summary.review}</b> need review</span>
      </div>
      <div className={styles.reviewSearch}>
        <label>
          <Search size={14} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search changed files..." />
        </label>
        <span>
          <Filter size={14} />
          <select value={operationFilter} onChange={(event) => setOperationFilter(event.target.value)} aria-label="Filter by operation">
            {operations.map((operation) => (
              <option key={operation} value={operation}>{operation === 'all' ? 'All operations' : operation}</option>
            ))}
          </select>
        </span>
        <select value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)} aria-label="Filter by risk">
          <option value="all">All risks</option>
          <option value="low">Low risk</option>
          <option value="medium">Medium risk</option>
          <option value="high">High risk</option>
          <option value="review">Needs review</option>
        </select>
      </div>
      <div className={styles.changedFiles}>
        {changeSet.files.length === 0 && <div className={styles.empty}>Patch review will appear after a worker records a change set.</div>}
        {changeSet.files.length > 0 && filteredFiles.length === 0 && <div className={styles.empty}>No changed files match the current filters.</div>}
        {filteredFiles.map((file) => (
          <article
            key={`${file.operation}-${file.path}`}
            data-selected={selectedPath === file.path}
            data-risk={file.reviewRequired ? 'review' : file.risk || 'low'}
            onClick={() => onSelectFile?.(file)}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') onSelectFile?.(file);
            }}
          >
            <strong>{file.path}</strong>
            <small>
              <b>{file.operation}</b>
              <i data-risk={file.reviewRequired ? 'review' : file.risk || 'low'}>{file.reviewRequired ? 'review required' : `${file.risk || 'low'} risk`}</i>
              {file.applied ? <em>applied</em> : <em>pending</em>}
            </small>
            <span><em>+{file.additions || 0}</em><i>-{file.deletions || 0}</i></span>
          </article>
        ))}
      </div>
      <div className={styles.reviewActions}>
        <button type="button" data-primary="true" disabled={!hasChanges} onClick={onApproveAll}>
          <CheckCircle2 size={14} /> Approve All
        </button>
        <button type="button" disabled={!hasChanges} onClick={onRejectAll}>
          <XCircle size={14} /> Reject All
        </button>
        <button type="button" disabled={!changeSet.rollbackAvailable} onClick={onRollback}>
          <RotateCcw size={14} /> Rollback
        </button>
      </div>
    </section>
  );
}
