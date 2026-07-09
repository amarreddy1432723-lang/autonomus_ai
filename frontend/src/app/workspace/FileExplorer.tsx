'use client';

import { useEffect, useRef } from 'react';
import { FileCode2, FileText, Folder, RefreshCw, Upload } from 'lucide-react';
import styles from './Workspace.module.css';

export type WorkspaceFile = {
  id: string;
  filename: string;
  content_type?: string;
  size_bytes?: number;
};

export type WorkspaceSearchMatch = {
  file_id: string;
  filename: string;
  line: number;
  snippet: string;
};

type Props = {
  files: WorkspaceFile[];
  selectedIds: string[];
  searchQuery: string;
  searchMatches: WorkspaceSearchMatch[];
  busy?: boolean;
  onRefresh: () => void;
  onToggleFile: (id: string) => void;
  onOpenFile: (file: WorkspaceFile) => void;
  onSearchChange: (value: string) => void;
  onSearch: () => void;
  onUpload: (files: FileList | null) => void;
  searchFocusKey?: number;
};

function fileIcon(filename: string) {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.py') || lower.endsWith('.ts') || lower.endsWith('.tsx') || lower.endsWith('.js') || lower.endsWith('.css') || lower.endsWith('.html')) {
    return <FileCode2 size={15} />;
  }
  return <FileText size={15} />;
}

export default function FileExplorer({
  files,
  selectedIds,
  searchQuery,
  searchMatches,
  busy,
  onRefresh,
  onToggleFile,
  onOpenFile,
  onSearchChange,
  onSearch,
  onUpload,
  searchFocusKey,
}: Props) {
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (searchFocusKey) {
      searchInputRef.current?.focus();
      searchInputRef.current?.select();
    }
  }, [searchFocusKey]);

  return (
    <aside className={styles.files}>
      <div className={styles.panelHeader}>
        <span>Project Files</span>
        <button className={styles.iconButton} type="button" onClick={onRefresh} disabled={busy} aria-label="Refresh files">
          <RefreshCw size={14} />
        </button>
      </div>
      <div className={styles.fileList}>
        <div className={styles.explorerSearch}>
          <input
            ref={searchInputRef}
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') onSearch();
            }}
            placeholder="Search workspace..."
          />
          <button type="button" onClick={onSearch} disabled={busy || !searchQuery.trim()}>
            Search
          </button>
        </div>
        {searchMatches.length > 0 && (
          <div className={styles.searchMatches}>
            {searchMatches.map((match) => (
              <button
                key={`${match.file_id}-${match.line}-${match.snippet}`}
                type="button"
                onClick={() => {
                  const file = files.find((item) => item.id === match.file_id);
                  if (file) onOpenFile(file);
                }}
              >
                <strong>{match.filename}:{match.line}</strong>
                <span>{match.snippet}</span>
              </button>
            ))}
          </div>
        )}
        <div className={styles.meta} style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '4px 0 10px' }}>
          <Folder size={14} /> Uploaded workspace
        </div>
        {files.map((file) => {
          const active = selectedIds.includes(file.id);
          return (
            <button
              key={file.id}
              className={`${styles.fileItem} ${active ? styles.fileItemActive : ''}`}
              type="button"
              onClick={() => {
                onToggleFile(file.id);
                onOpenFile(file);
              }}
              title={file.filename}
            >
              {fileIcon(file.filename)}
              <span className={styles.fileName}>{file.filename}</span>
            </button>
          );
        })}
        {files.length === 0 && <div className={styles.meta}>Upload files, PDFs, docs, or code to make NEXUS read them internally.</div>}
      </div>
      <div className={styles.uploadBox}>
        <label className={styles.uploadLabel}>
          <span>
            <Upload size={18} />
            <br />
            Drop or choose files
          </span>
          <input
            hidden
            multiple
            type="file"
            accept=".txt,.md,.json,.csv,.py,.js,.ts,.tsx,.html,.css,.pdf,.docx,.xlsx,.zip"
            onChange={(event) => onUpload(event.target.files)}
          />
        </label>
      </div>
    </aside>
  );
}
