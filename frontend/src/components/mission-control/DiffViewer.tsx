import { useMemo, useState } from 'react';
import styles from './MissionControlProduct.module.css';
import type { MissionControlChangeFile, MissionControlChangeSet, MissionControlVerificationStep } from './types';

function fallbackDiff(file?: MissionControlChangeFile) {
  if (!file) {
    return ['# No recorded patch yet', 'Run a mission task that produces a change set to inspect the diff.'];
  }
  return [
    `diff --git a/${file.path} b/${file.path}`,
    `--- a/${file.path}`,
    `+++ b/${file.path}`,
    `@@ ${file.operation} @@`,
    `+ ${file.operation} recorded for ${file.path}`,
    file.reviewRequired ? `! Review required before apply` : `+ Safe operation`,
  ];
}

function checksForFile(file: MissionControlChangeFile | undefined, verification: MissionControlVerificationStep[]) {
  if (!file) return [];
  const lowerPath = file.path.toLowerCase();
  return verification.filter((check) => {
    const haystack = `${check.label} ${check.command || ''} ${check.summary || ''}`.toLowerCase();
    return haystack.includes(lowerPath) || lowerPath.split(/[\\/]/).some((part) => part.length > 3 && haystack.includes(part));
  });
}

export function DiffViewer({
  changeSet,
  selectedPath,
  onSelectFile,
  verification = [],
}: {
  changeSet: MissionControlChangeSet;
  selectedPath?: string;
  onSelectFile?: (file: MissionControlChangeFile) => void;
  verification?: MissionControlVerificationStep[];
}) {
  const [tab, setTab] = useState<'diff' | 'original' | 'proposed'>('diff');
  const [mode, setMode] = useState<'unified' | 'side'>('unified');
  const selectedFile = useMemo(
    () => changeSet.files.find((file) => file.path === selectedPath) || changeSet.files.find((file) => file.diff) || changeSet.files[0],
    [changeSet.files, selectedPath],
  );
  const relatedChecks = useMemo(() => checksForFile(selectedFile, verification), [selectedFile, verification]);
  const lines = useMemo(() => (selectedFile?.diff ? selectedFile.diff.split(/\r?\n/) : fallbackDiff(selectedFile)), [selectedFile]);

  return (
    <section className={styles.panel} aria-label="Diff viewer">
      <header>
        <div>
          <h3>{selectedFile ? selectedFile.path : 'Diff Viewer'}</h3>
          <p>
            {selectedFile
              ? `${selectedFile.operation} · ${selectedFile.reviewRequired ? 'review required' : `${selectedFile.risk || 'low'} risk`} · +${selectedFile.additions || 0}/-${selectedFile.deletions || 0}`
              : 'Original, unified diff, and proposed output for the active change set.'}
          </p>
        </div>
        <div className={styles.segmented}>
          {(['original', 'diff', 'proposed'] as const).map((item) => (
            <button key={item} type="button" data-active={tab === item} onClick={() => setTab(item)}>{item}</button>
          ))}
        </div>
      </header>
      {changeSet.files.length > 1 && (
        <div className={styles.fileStrip} aria-label="Changed file tabs">
          {changeSet.files.map((file) => (
            <button
              key={file.path}
              type="button"
              data-active={selectedFile?.path === file.path}
              data-risk={file.reviewRequired ? 'review' : file.risk || 'low'}
              onClick={() => onSelectFile?.(file)}
            >
              {file.path.split(/[\\/]/).pop() || file.path}
            </button>
          ))}
        </div>
      )}
      <div className={styles.diffToolbar}>
        <button type="button" data-active={mode === 'unified'} onClick={() => setMode('unified')}>Unified</button>
        <button type="button" data-active={mode === 'side'} onClick={() => setMode('side')}>Side by side</button>
      </div>
      <div className={styles.fileVerification}>
        {relatedChecks.length === 0 ? (
          <span>No file-specific verification recorded yet.</span>
        ) : (
          relatedChecks.slice(0, 3).map((check) => (
            <span key={check.id} data-state={check.status}>{check.label}: {check.status.replace(/_/g, ' ')}</span>
          ))
        )}
      </div>
      <pre className={styles.diffPane} data-mode={mode} data-tab={tab}>
        {lines.map((line, index) => (
          <code
            key={`${index}-${line}`}
            data-line={line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : line.startsWith('!') ? 'warn' : 'ctx'}
          >
            {line}
          </code>
        ))}
      </pre>
    </section>
  );
}
