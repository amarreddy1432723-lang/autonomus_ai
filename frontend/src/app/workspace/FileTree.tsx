'use client';

import { ChevronDown, ChevronRight, FileCode2, FileJson, FileText, Folder, FolderOpen, Pencil, Plus, Trash2 } from 'lucide-react';
import { KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';
import type { WorkspaceFile } from './FileExplorer';
import styles from './Workspace.module.css';

type TreeNode = {
  id: string;
  name: string;
  path: string;
  type: 'folder' | 'file';
  file?: WorkspaceFile;
  children: TreeNode[];
  childMap?: Map<string, TreeNode>;
};

type Props = {
  files: WorkspaceFile[];
  selectedIds: string[];
  activePath?: string;
  busy?: boolean;
  dirtyIds?: string[];
  dirtyPaths?: string[];
  rootPath?: string;
  filter?: string;
  onOpenFile: (file: WorkspaceFile) => void;
  onToggleFile: (id: string) => void;
  onCreateItem?: (type: 'file' | 'folder', basePath?: string) => void;
  onRenameFile?: (file: WorkspaceFile, nextPath?: string) => void;
  onDeleteFile?: (file: WorkspaceFile) => void;
  onRevealPath?: (relativePath: string) => void;
};

function fileIcon(filename: string) {
  const lower = filename.toLowerCase();
  const className =
    /\.(ts|tsx)$/.test(lower) ? styles.fileIconTs
      : /\.(js|jsx)$/.test(lower) ? styles.fileIconJs
      : /\.py$/.test(lower) ? styles.fileIconPy
      : /\.json$/.test(lower) ? styles.fileIconJson
      : /\.md$/.test(lower) ? styles.fileIconMd
      : '';
  if (/\.json$/.test(lower)) return <FileJson className={className} size={12} />;
  if (/\.md$/.test(lower)) return <FileText className={className} size={12} />;
  if (/\.(py|ts|tsx|js|jsx|css|html|yml|yaml|toml)$/.test(lower)) return <FileCode2 className={className} size={12} />;
  return <FileText size={12} />;
}

function isGeneratedOrIgnoredPath(value: string) {
  const normalized = value.replace(/\\/g, '/').toLowerCase();
  return /(^|\/)(node_modules|\.git|__pycache__|pycache|\.next|dist|build|coverage)(\/|$)/.test(normalized)
    || /\.(pyc|pyo|map|min\.js)$/.test(normalized);
}

function normalizeTreePath(value?: string) {
  return String(value || '').replace(/\\/g, '/').replace(/^\/+/, '').toLowerCase();
}

function buildTree(files: WorkspaceFile[]): TreeNode[] {
  const root: TreeNode = { id: 'root', name: '', path: '', type: 'folder', children: [], childMap: new Map() };
  const ensureFolder = (path: string, name: string, parent: TreeNode) => {
    parent.childMap ||= new Map();
    let folder = parent.childMap.get(name);
    if (!folder) {
      folder = { id: `folder:${path}`, name, path, type: 'folder', children: [], childMap: new Map() };
      parent.childMap.set(name, folder);
    }
    return folder;
  };

  for (const file of files) {
    const parts = file.filename.replace(/\\/g, '/').split('/').filter(Boolean);
    if (file.kind === 'folder') {
      let parent = root;
      let currentPath = '';
      for (const part of parts) {
        currentPath = currentPath ? `${currentPath}/${part}` : part;
        parent = ensureFolder(currentPath, part, parent);
      }
      continue;
    }
    let parent = root;
    let currentPath = '';
    for (let index = 0; index < parts.length; index += 1) {
      const part = parts[index];
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isFile = index === parts.length - 1;
      if (isFile) {
        parent.childMap ||= new Map();
        parent.childMap.set(`file:${file.id}`, {
          id: file.id,
          name: part,
          path: currentPath,
          type: 'file',
          file,
          children: [],
        });
      } else {
        parent = ensureFolder(currentPath, part, parent);
      }
    }
  }

  const materialize = (node: TreeNode): TreeNode => ({
    ...node,
    children: Array.from(node.childMap?.values() || []).map(materialize),
    childMap: undefined,
  });

  const sortNodes = (nodes: TreeNode[]): TreeNode[] => nodes
    .map((node) => ({ ...node, children: sortNodes(node.children), childMap: undefined }))
    .sort((left, right) => {
      if (left.type !== right.type) return left.type === 'folder' ? -1 : 1;
      return left.name.localeCompare(right.name);
    });

  return sortNodes(materialize(root).children);
}

function TreeRow({
  node,
  depth,
  selectedIds,
  dirtyIds,
  dirtyPaths,
  activePath,
  rootPath,
  busy,
  expanded,
  focusId,
  setFocusId,
  onToggleExpand,
  onOpenFile,
  onToggleFile,
  onCreateItem,
  onRenameFile,
  onDeleteFile,
  onRevealPath,
}: {
  node: TreeNode;
  depth: number;
  selectedIds: string[];
  dirtyIds: string[];
  dirtyPaths: string[];
  activePath?: string;
  rootPath?: string;
  busy?: boolean;
  expanded: Set<string>;
  focusId: string;
  setFocusId: (id: string) => void;
  onToggleExpand: (path: string) => void;
  onOpenFile: (file: WorkspaceFile) => void;
  onToggleFile: (id: string) => void;
  onCreateItem?: (type: 'file' | 'folder', basePath?: string) => void;
  onRenameFile?: (file: WorkspaceFile, nextPath?: string) => void;
  onDeleteFile?: (file: WorkspaceFile) => void;
  onRevealPath?: (relativePath: string) => void;
}) {
  const isExpanded = expanded.has(node.path);
  const isContextSelected = node.file ? selectedIds.includes(node.file.id) : false;
  const isActive = Boolean(activePath && normalizeTreePath(node.path) === normalizeTreePath(activePath));
  const isDirty = Boolean(node.file && (dirtyIds.includes(node.file.id) || dirtyPaths.includes(normalizeTreePath(node.file.filename))));
  const isGenerated = isGeneratedOrIgnoredPath(node.path);
  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(node.path);
  const rowRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (focusId === node.id) rowRef.current?.focus();
  }, [focusId, node.id]);

  useEffect(() => {
    setRenameValue(node.path);
  }, [node.path]);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (node.type === 'folder') onToggleExpand(node.path);
      if (node.file) {
        onToggleFile(node.file.id);
        onOpenFile(node.file);
      }
    }
    if (event.key === 'ArrowRight' && node.type === 'folder' && !isExpanded) onToggleExpand(node.path);
    if (event.key === 'ArrowLeft' && node.type === 'folder' && isExpanded) onToggleExpand(node.path);
    if (event.key === 'Delete' && node.file && onDeleteFile) {
      event.preventDefault();
      onDeleteFile(node.file);
    }
    if (event.key === 'F2' && node.file && onRenameFile) {
      event.preventDefault();
      setRenaming(true);
    }
  };
  const openFile = () => {
    if (!node.file) return;
    onToggleFile(node.file.id);
    onOpenFile(node.file);
  };
  const createBase = node.type === 'folder' ? node.path : node.path.split('/').slice(0, -1).join('/');
  const copyText = async (value: string) => {
    try {
      await navigator.clipboard?.writeText(value);
    } catch {
      // Clipboard is best-effort.
    }
  };
  const finishRename = () => {
    const nextPath = renameValue.trim().replace(/\\/g, '/');
    setRenaming(false);
    if (!node.file || !onRenameFile || !nextPath || nextPath === node.path) return;
    onRenameFile(node.file, nextPath);
  };

  return (
    <>
      <div
        className={`${styles.fileTreeRow} ${isActive ? styles.fileTreeRowActive : ''} ${isDirty ? styles.fileTreeRowDirty : ''} ${isGenerated ? styles.fileTreeRowGenerated : ''}`}
        data-context-selected={isContextSelected ? 'true' : 'false'}
        style={{ paddingLeft: depth * 12 }}
        onMouseEnter={() => setFocusId(node.id)}
        onContextMenu={(event) => {
          event.preventDefault();
          setMenuOpen((value) => !value);
        }}
      >
        <button
          ref={rowRef}
          type="button"
          className={styles.fileTreeOpen}
          title={node.path}
          onKeyDown={onKeyDown}
          onClick={() => {
            if (node.type === 'folder') onToggleExpand(node.path);
            if (node.file) openFile();
          }}
        >
          {node.type === 'folder' ? (
            <>
              {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              {isExpanded ? <FolderOpen size={12} /> : <Folder size={12} />}
            </>
          ) : (
            <>
              <span className={styles.fileTreeSpacer} />
              {fileIcon(node.name)}
            </>
          )}
          {renaming ? (
            <input
              className={styles.fileTreeRenameInput}
              value={renameValue}
              autoFocus
              onChange={(event) => setRenameValue(event.target.value)}
              onClick={(event) => event.stopPropagation()}
              onKeyDown={(event) => {
                if (event.key === 'Enter') finishRename();
                if (event.key === 'Escape') setRenaming(false);
              }}
              onBlur={finishRename}
            />
          ) : (
            <span>{node.name}</span>
          )}
          {isDirty && <i className={styles.fileTreeDirtyDot} title="Unsaved changes" />}
        </button>
        {node.file && (onRenameFile || onDeleteFile) && (
          <span className={styles.fileTreeActions}>
            {onRenameFile && (
              <button type="button" disabled={busy} title="Rename" onClick={() => node.file && onRenameFile(node.file)}>
                <Pencil size={12} />
              </button>
            )}
            {onDeleteFile && (
              <button type="button" disabled={busy} title="Delete" onClick={() => node.file && onDeleteFile(node.file)}>
                <Trash2 size={12} />
              </button>
            )}
          </span>
        )}
        {menuOpen && (
          <div className={styles.fileTreeContextMenu} onMouseLeave={() => setMenuOpen(false)}>
            {node.file && <button type="button" onClick={() => { openFile(); setMenuOpen(false); }}>Open</button>}
            {onCreateItem && <button type="button" onClick={() => { onCreateItem('file', createBase); setMenuOpen(false); }}><Plus size={12} /> New File</button>}
            {onCreateItem && <button type="button" onClick={() => { onCreateItem('folder', createBase); setMenuOpen(false); }}><Folder size={12} /> New Folder</button>}
            {node.file && onRenameFile && <button type="button" onClick={() => { setRenaming(true); setMenuOpen(false); }}>Rename</button>}
            {node.file && onDeleteFile && <button type="button" onClick={() => { node.file && onDeleteFile(node.file); setMenuOpen(false); }}>Delete</button>}
            <button type="button" onClick={() => { void copyText(node.path); setMenuOpen(false); }}>Copy Relative Path</button>
            {rootPath && <button type="button" onClick={() => { void copyText(`${rootPath.replace(/\\/g, '/')}/${node.path}`); setMenuOpen(false); }}>Copy Absolute Path</button>}
            {onRevealPath && <button type="button" onClick={() => { onRevealPath(node.path); setMenuOpen(false); }}>Reveal in Explorer</button>}
          </div>
        )}
      </div>
      {node.type === 'folder' && isExpanded && node.children.map((child) => (
        <TreeRow
          key={child.id}
          node={child}
          depth={depth + 1}
          selectedIds={selectedIds}
          dirtyIds={dirtyIds}
          dirtyPaths={dirtyPaths}
          activePath={activePath}
          rootPath={rootPath}
          busy={busy}
          expanded={expanded}
          focusId={focusId}
          setFocusId={setFocusId}
          onToggleExpand={onToggleExpand}
          onOpenFile={onOpenFile}
          onToggleFile={onToggleFile}
          onCreateItem={onCreateItem}
          onRenameFile={onRenameFile}
          onDeleteFile={onDeleteFile}
          onRevealPath={onRevealPath}
        />
      ))}
    </>
  );
}

function filterTree(nodes: TreeNode[], query: string): TreeNode[] {
  const value = query.trim().toLowerCase();
  if (!value) return nodes;
  return nodes
    .map((node) => {
      const children = filterTree(node.children, value);
      const match = node.path.toLowerCase().includes(value) || node.name.toLowerCase().includes(value);
      return match || children.length ? { ...node, children } : null;
    })
    .filter(Boolean) as TreeNode[];
}

export default function FileTree({ files, selectedIds, activePath = '', dirtyIds = [], dirtyPaths = [], rootPath, filter = '', busy, onOpenFile, onToggleFile, onCreateItem, onRenameFile, onDeleteFile, onRevealPath }: Props) {
  const fullTree = useMemo(() => buildTree(files), [files]);
  const tree = useMemo(() => filterTree(fullTree, filter), [filter, fullTree]);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(tree.filter((node) => node.type === 'folder').map((node) => node.path)));
  const [focusId, setFocusId] = useState('');
  const initializedTreeRef = useRef(false);
  const activeFolderPath = activePath.split('/').slice(0, -1).join('/');

  useEffect(() => {
    const folderPaths = new Set<string>();
    const collectFolders = (nodes: TreeNode[]) => nodes.forEach((node) => {
      if (node.type === 'folder') {
        folderPaths.add(node.path);
        collectFolders(node.children);
      }
    });
    collectFolders(fullTree);

    setExpanded((current) => {
      if (!initializedTreeRef.current) {
        initializedTreeRef.current = true;
        return folderPaths;
      }
      const next = new Set(Array.from(current).filter((path) => folderPaths.has(path)));
      if (activeFolderPath) {
        let currentPath = '';
        for (const part of activeFolderPath.split('/').filter(Boolean)) {
          currentPath = currentPath ? `${currentPath}/${part}` : part;
          if (folderPaths.has(currentPath)) next.add(currentPath);
        }
      }
      return next;
    });
  }, [activeFolderPath, fullTree]);

  const toggleExpand = (path: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  return (
    <div className={styles.fileTree} role="tree" aria-label="Workspace file tree">
      {tree.map((node) => (
        <TreeRow
          key={node.id}
          node={node}
          depth={0}
          selectedIds={selectedIds}
          dirtyIds={dirtyIds}
          dirtyPaths={dirtyPaths.map(normalizeTreePath)}
          activePath={activePath}
          rootPath={rootPath}
          busy={busy}
          expanded={expanded}
          focusId={focusId}
          setFocusId={setFocusId}
          onToggleExpand={toggleExpand}
          onOpenFile={onOpenFile}
          onToggleFile={onToggleFile}
          onCreateItem={onCreateItem}
          onRenameFile={onRenameFile}
          onDeleteFile={onDeleteFile}
          onRevealPath={onRevealPath}
        />
      ))}
    </div>
  );
}
