'use client';

import { useEffect, useRef } from 'react';
import { FolderOpen, GitBranch, FolderPlus, Plus, RefreshCw, Search, Upload } from 'lucide-react';
import FileTree from './FileTree';
import styles from './Workspace.module.css';

export type WorkspaceFile = {
  id: string;
  filename: string;
  content_type?: string;
  size_bytes?: number;
  kind?: 'file' | 'folder';
  source?: 'backend' | 'local';
};

export type WorkspaceSearchMatch = {
  file_id: string;
  filename: string;
  line: number;
  snippet: string;
  kind?: 'file' | 'symbol' | 'dependency' | 'route' | 'text';
  score?: number;
  symbol?: string | null;
};

type Props = {
  files: WorkspaceFile[];
  selectedIds: string[];
  activePath?: string;
  searchQuery: string;
  searchMatches: WorkspaceSearchMatch[];
  busy?: boolean;
  onRefresh: () => void;
  onToggleFile: (id: string) => void;
  onOpenFile: (file: WorkspaceFile) => void;
  onSearchChange: (value: string) => void;
  onSearch: () => void;
  onUpload: (files: FileList | null) => void;
  onCreateItem?: (type: 'file' | 'folder') => void;
  onCreateItemAtPath?: (type: 'file' | 'folder', basePath?: string) => void;
  onRenameFile?: (file: WorkspaceFile, nextPath?: string) => void;
  onDeleteFile?: (file: WorkspaceFile) => void;
  onRevealPath?: (relativePath: string) => void;
  searchFocusKey?: number;
  dirtyIds?: string[];
  dirtyPaths?: string[];
  rootPath?: string;
};

function searchKindLabel(kind?: WorkspaceSearchMatch['kind']) {
  if (kind === 'symbol') return 'Symbol';
  if (kind === 'dependency') return 'Import';
  if (kind === 'route') return 'Route';
  if (kind === 'file') return 'File';
  return 'Text';
}

export default function FileExplorer({
  files,
  selectedIds,
  activePath,
  searchQuery,
  searchMatches,
  busy,
  onRefresh,
  onToggleFile,
  onOpenFile,
  onSearchChange,
  onSearch,
  onUpload,
  onCreateItem,
  onCreateItemAtPath,
  onRenameFile,
  onDeleteFile,
  onRevealPath,
  searchFocusKey,
  dirtyIds = [],
  dirtyPaths = [],
  rootPath,
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
        <span>MY AI</span>
        <div className={styles.fileToolbar}>
          <button className={styles.iconButton} type="button" onClick={() => onCreateItem?.('file')} disabled={busy || !onCreateItem} title="New file">
            <Plus size={14} />
          </button>
          <button className={styles.iconButton} type="button" onClick={() => onCreateItem?.('folder')} disabled={busy || !onCreateItem} title="New folder">
            <FolderPlus size={14} />
          </button>
          <button className={styles.iconButton} type="button" onClick={() => searchInputRef.current?.focus()} title="Search files">
            <Search size={14} />
          </button>
          <button className={styles.iconButton} type="button" disabled title="Git status">
            <GitBranch size={14} />
          </button>
          <button className={styles.iconButton} type="button" onClick={onRefresh} disabled={busy} title="Refresh files">
            <RefreshCw size={14} />
          </button>
        </div>
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
          <button type="button" onClick={onSearch} disabled={busy || !searchQuery.trim()} title="Run search">
            <Search size={14} />
          </button>
        </div>
        {searchMatches.length > 0 && (
          <div className={styles.searchMatches}>
            {searchMatches.map((match) => (
              <button
                key={`${match.file_id}-${match.line}-${match.kind || 'text'}-${match.symbol || match.snippet}`}
                type="button"
                onClick={() => {
                  const file = files.find((item) => item.id === match.file_id);
                  if (file) onOpenFile(file);
                }}
              >
                <strong>
                  <span>{searchKindLabel(match.kind)}</span>
                  {match.filename}:{match.line}
                </strong>
                {match.symbol && <em>{match.symbol}</em>}
                <span>{match.snippet}</span>
              </button>
            ))}
          </div>
        )}
        <div className={styles.meta} style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '4px 0 10px' }}>
          <FolderOpen size={14} /> Uploaded workspace
        </div>
        <FileTree
          files={files}
          selectedIds={selectedIds}
          activePath={activePath}
          dirtyIds={dirtyIds}
          dirtyPaths={dirtyPaths}
          rootPath={rootPath}
          filter={searchQuery}
          busy={busy}
          onOpenFile={onOpenFile}
          onToggleFile={onToggleFile}
          onCreateItem={onCreateItemAtPath || ((type) => onCreateItem?.(type))}
          onRenameFile={onRenameFile}
          onDeleteFile={onDeleteFile}
          onRevealPath={onRevealPath}
        />
        {files.length === 0 && <div className={styles.meta}>Upload files, PDFs, docs, or code to make Arceus read them internally.</div>}
      </div>
      <div className={styles.uploadBox}>
        <label className={styles.uploadLabel}>
          <span>
            <Upload size={15} />
            <strong>Drop or choose files</strong>
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
