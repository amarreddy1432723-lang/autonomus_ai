'use client';

import dynamic from 'next/dynamic';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronLeft, ChevronRight, FileCode2, RotateCcw, X } from 'lucide-react';
import styles from './Workspace.module.css';
import type { PatchPreviewItem } from './ActivityPanel';

const MonacoDiffEditor = dynamic(() => import('@monaco-editor/react').then((mod) => mod.DiffEditor), {
  ssr: false,
  loading: () => <div className={styles.diffViewerLoading}>Loading diff...</div>,
});

type Props = {
  patch: PatchPreviewItem;
  canApply: boolean;
  hasPatch: boolean;
  onApplySelection: (selection: { fileIds?: string[]; operationIds?: string[]; hunkIds?: string[] }) => void;
  onRejectSelection: (selection: { fileIds?: string[]; operationIds?: string[] }) => void;
  onApproveHunk: (hunkId: string) => void;
  onRejectHunk: (hunkId: string) => void;
  onResetPatchReview: () => void;
};

function operationLabel(operation?: string) {
  switch ((operation || 'modify').toLowerCase()) {
    case 'create':
      return 'NEW FILE';
    case 'delete':
      return 'DELETED';
    case 'rename':
      return 'RENAMED';
    case 'folder':
      return 'NEW FOLDER';
    default:
      return 'MODIFIED';
  }
}

function operationTone(operation?: string) {
  switch ((operation || 'modify').toLowerCase()) {
    case 'create':
      return 'new';
    case 'delete':
      return 'deleted';
    case 'rename':
      return 'renamed';
    case 'folder':
      return 'folder';
    default:
      return 'modified';
  }
}

function diffStats(diff: string) {
  return diff.split('\n').reduce(
    (stats, line) => {
      if (line.startsWith('+') && !line.startsWith('+++')) stats.additions += 1;
      if (line.startsWith('-') && !line.startsWith('---')) stats.deletions += 1;
      return stats;
    },
    { additions: 0, deletions: 0 }
  );
}

function hunkText(patch: PatchPreviewItem) {
  const hunks = patch.hunks || [];
  const original = hunks.flatMap((hunk) => hunk.old_lines || []).join('\n');
  const modified = hunks.flatMap((hunk) => hunk.new_lines || []).join('\n');
  if (original || modified) return { original, modified };

  const oldLines: string[] = [];
  const newLines: string[] = [];
  for (const line of (patch.diff || '').split('\n')) {
    if (line.startsWith('---') || line.startsWith('+++') || line.startsWith('@@')) continue;
    if (line.startsWith('-')) oldLines.push(line.slice(1));
    else if (line.startsWith('+')) newLines.push(line.slice(1));
    else if (line.startsWith(' ')) {
      oldLines.push(line.slice(1));
      newLines.push(line.slice(1));
    }
  }
  return { original: oldLines.join('\n'), modified: newLines.join('\n') };
}

function hunkSideBySide(hunk: NonNullable<PatchPreviewItem['hunks']>[number]) {
  const original = (hunk.old_lines || []).join('\n');
  const modified = (hunk.new_lines || []).join('\n');
  if (original || modified) return { original, modified };
  const oldLines: string[] = [];
  const newLines: string[] = [];
  for (const line of hunk.lines || []) {
    if (line.startsWith('-')) oldLines.push(line.slice(1));
    else if (line.startsWith('+')) newLines.push(line.slice(1));
    else {
      oldLines.push(line.replace(/^ /, ''));
      newLines.push(line.replace(/^ /, ''));
    }
  }
  return { original: oldLines.join('\n'), modified: newLines.join('\n') };
}

function operationBadgeText(patch: PatchPreviewItem) {
  const operation = (patch.operation || 'modify').toLowerCase();
  if (operation === 'rename') return `RENAMED ← ${patch.filename}`;
  return operationLabel(operation);
}

function selectionForPatch(patch: PatchPreviewItem) {
  return patch.file_id
    ? { fileIds: [patch.file_id], operationIds: patch.operation_id ? [patch.operation_id] : [] }
    : { operationIds: patch.operation_id ? [patch.operation_id] : [] };
}

export default function DiffViewer({
  patch,
  canApply,
  hasPatch,
  onApplySelection,
  onRejectSelection,
  onApproveHunk,
  onRejectHunk,
  onResetPatchReview,
}: Props) {
  const hunkRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [activeHunkIndex, setActiveHunkIndex] = useState(0);
  const stats = {
    additions: patch.additions ?? diffStats(patch.diff || '').additions,
    deletions: patch.deletions ?? diffStats(patch.diff || '').deletions,
  };
  const { original, modified } = hunkText(patch);
  const hasSideBySide = Boolean(original || modified);
  const selected = selectionForPatch(patch);
  const hunks = patch.hunks || [];
  const approvedHunkIds = useMemo(() => hunks.filter((hunk) => hunk.status === 'approved').map((hunk) => hunk.id), [hunks]);
  const visibleHunkIds = useMemo(() => hunks.map((hunk) => hunk.id), [hunks]);
  const applyHunkIds = approvedHunkIds.length ? approvedHunkIds : visibleHunkIds.filter((id) => {
    const hunk = hunks.find((item) => item.id === id);
    return hunk?.status !== 'rejected';
  });
  const allHunksRejected = hunks.length > 0 && hunks.every((hunk) => hunk.status === 'rejected');
  const canApplyCurrentSelection = canApply && !allHunksRejected;

  const focusHunk = (nextIndex: number) => {
    if (!visibleHunkIds.length) return;
    const bounded = (nextIndex + visibleHunkIds.length) % visibleHunkIds.length;
    setActiveHunkIndex(bounded);
    hunkRefs.current[visibleHunkIds[bounded]]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!event.altKey || !visibleHunkIds.length) return;
      if (event.key === ']') {
        event.preventDefault();
        focusHunk(activeHunkIndex + 1);
      }
      if (event.key === '[') {
        event.preventDefault();
        focusHunk(activeHunkIndex - 1);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeHunkIndex, visibleHunkIds]);

  if ((patch.operation || '').toLowerCase() === 'folder') {
    return (
      <div className={styles.diffViewer}>
        <div className={styles.diffViewerHeader}>
          <span><FileCode2 size={14} /> <strong className={styles.diffOperationBadge} data-operation={operationTone(patch.operation)}>{operationLabel(patch.operation)}</strong></span>
          <strong>{patch.filename}</strong>
        </div>
        <div className={styles.diffFolderRow}>Folder will be created when this operation is approved.</div>
        <div className={styles.changeActions}>
          <button type="button" onClick={() => onApplySelection(selected)} disabled={!canApply}><Check size={14} /> Apply folder</button>
          <button type="button" onClick={() => onRejectSelection(selected)} disabled={!hasPatch}><X size={14} /> Reject folder</button>
          <button type="button" onClick={onResetPatchReview} disabled={!hasPatch}><RotateCcw size={14} /> Reset review</button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.diffViewer}>
      <div className={styles.diffViewerHeader}>
          <span><FileCode2 size={14} /> <strong className={styles.diffOperationBadge} data-operation={operationTone(patch.operation)}>{operationBadgeText(patch)}</strong></span>
        <strong>{patch.new_filename || patch.filename}</strong>
        <em>
          {patch.conflict ? 'conflict · ' : ''}
          {patch.new_filename ? `from ${patch.filename} · ` : ''}
          +{stats.additions} / -{stats.deletions}
        </em>
      </div>
      {patch.conflict && (
        <div className={styles.diffConflictBanner}>
          File was modified since this patch was generated. Review carefully before applying.
        </div>
      )}
      <div className={styles.diffViewerToolbar}>
        <button type="button" onClick={() => focusHunk(activeHunkIndex - 1)} disabled={!visibleHunkIds.length}>
          <ChevronLeft size={13} />
          Prev hunk
        </button>
        <button type="button" onClick={() => focusHunk(activeHunkIndex + 1)} disabled={!visibleHunkIds.length}>
          <ChevronRight size={13} />
          Next hunk
        </button>
        <button type="button" onClick={() => onApplySelection({ hunkIds: visibleHunkIds })} disabled={!canApply || !visibleHunkIds.length}>
          Accept all
        </button>
        <button type="button" onClick={() => onRejectSelection(selected)} disabled={!hasPatch}>
          Reject all
        </button>
      </div>

      {!!hunks.length && (
        <div className={styles.hunkNavigator}>
          {hunks.map((hunk, index) => {
            const hunkAdditions = hunk.additions ?? (hunk.lines || []).filter((line) => line.startsWith('+') && !line.startsWith('+++')).length;
            const hunkDeletions = hunk.deletions ?? (hunk.lines || []).filter((line) => line.startsWith('-') && !line.startsWith('---')).length;
            return (
              <div
                className={`${styles.hunkNavItem} ${index === activeHunkIndex ? styles.hunkNavItemActive : ''}`}
                key={hunk.id}
                ref={(node) => { hunkRefs.current[hunk.id] = node; }}
              >
                <div>
                  <strong>Hunk {hunk.index + 1}</strong>
                  <span>{hunk.status || 'pending'} · +{hunkAdditions} / -{hunkDeletions}</span>
                </div>
                <div>
                  <button type="button" onClick={() => onApproveHunk(hunk.id)} disabled={!canApply}>Accept</button>
                  <button type="button" onClick={() => onRejectHunk(hunk.id)} disabled={!hasPatch}>Reject</button>
                  <button type="button" onClick={() => onApplySelection({ hunkIds: [hunk.id] })} disabled={!canApply}>Apply</button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {hunks.length > 0 ? (
        <div className={styles.hunkDiffStack}>
          {hunks.map((hunk, index) => {
            const sideBySide = hunkSideBySide(hunk);
            return (
              <div
                className={`${styles.hunkDiffBlock} ${index === activeHunkIndex ? styles.hunkDiffBlockActive : ''}`}
                key={`diff-${hunk.id}`}
                ref={(node) => { hunkRefs.current[hunk.id] = node; }}
              >
                <div className={styles.hunkDiffHeader}>
                  <strong>{hunk.header || `Hunk ${hunk.index + 1}`}</strong>
                  <span>{hunk.status || 'pending'}</span>
                </div>
                <div className={styles.diffViewerEditor}>
                  <MonacoDiffEditor
                    original={sideBySide.original}
                    modified={sideBySide.modified}
                    language="typescript"
                    theme="vs-dark"
                    options={{
                      readOnly: true,
                      minimap: { enabled: false },
                      renderSideBySide: true,
                      scrollBeyondLastLine: false,
                      fontSize: 12,
                      lineNumbersMinChars: 3,
                      automaticLayout: true,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      ) : hasSideBySide ? (
        <div className={styles.diffViewerEditor}>
          <MonacoDiffEditor
            original={original}
            modified={modified}
            language="typescript"
            theme="vs-dark"
            options={{
              readOnly: true,
              minimap: { enabled: false },
              renderSideBySide: true,
              scrollBeyondLastLine: false,
              fontSize: 12,
              lineNumbersMinChars: 3,
              automaticLayout: true,
            }}
          />
        </div>
      ) : (
        <pre className={styles.diffViewerFallback}>{patch.diff || 'No line diff for this operation.'}</pre>
      )}

      <div className={styles.changeActions}>
        <button
          type="button"
          onClick={() => onApplySelection(applyHunkIds.length ? { hunkIds: applyHunkIds } : selected)}
          disabled={!canApplyCurrentSelection}
          title={allHunksRejected ? 'All hunks rejected' : undefined}
        >
          <Check size={14} /> Apply selected
        </button>
        <button type="button" onClick={() => onRejectSelection(selected)} disabled={!hasPatch}><X size={14} /> Reject selected</button>
        <button type="button" onClick={onResetPatchReview} disabled={!hasPatch}><RotateCcw size={14} /> Reset review</button>
      </div>
    </div>
  );
}
