'use client';

import dynamic from 'next/dynamic';
import { Braces, Code2, Save, Wand2, X, Minimize2, Maximize2 } from 'lucide-react';
import { useRef, useState } from 'react';
import styles from './Workspace.module.css';

const MonacoEditor = dynamic(() => import('@monaco-editor/react'), {
  ssr: false,
  loading: () => <div className={styles.editorLoading}>Loading editor...</div>,
});

export type OpenWorkspaceFile = {
  id: string;
  filename: string;
  content: string;
  dirty: boolean;
};

type Props = {
  file: OpenWorkspaceFile | null;
  tabs: OpenWorkspaceFile[];
  activeFileId: string;
  busy: boolean;
  onChange: (content: string) => void;
  onSave: () => void;
  onSelectTab: (fileId: string) => void;
  onCloseTab: (fileId: string) => void;
  onInlineEdit: (instruction: string, selectedText: string, start: number, end: number) => void;
  onComplete: (cursor: number) => void;
  onToggleExpand?: () => void;
  isCollapsed?: boolean;
};

function languageLabel(filename: string) {
  const extension = filename.split('.').pop()?.toLowerCase();
  if (!extension) return 'text';
  if (extension === 'tsx') return 'React TSX';
  if (extension === 'ts') return 'TypeScript';
  if (extension === 'js') return 'JavaScript';
  if (extension === 'py') return 'Python';
  if (extension === 'json') return 'JSON';
  if (extension === 'md') return 'Markdown';
  return extension.toUpperCase();
}

function monacoLanguage(filename: string) {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.tsx')) return 'typescript';
  if (lower.endsWith('.ts')) return 'typescript';
  if (lower.endsWith('.jsx')) return 'javascript';
  if (lower.endsWith('.js')) return 'javascript';
  if (lower.endsWith('.py')) return 'python';
  if (lower.endsWith('.json')) return 'json';
  if (lower.endsWith('.md')) return 'markdown';
  if (lower.endsWith('.css')) return 'css';
  if (lower.endsWith('.html')) return 'html';
  if (lower.endsWith('.yml') || lower.endsWith('.yaml')) return 'yaml';
  return 'plaintext';
}

export default function EditorPanel({ file, tabs, activeFileId, busy, onChange, onSave, onSelectTab, onCloseTab, onInlineEdit, onComplete, onToggleExpand, isCollapsed }: Props) {
  const editorRef = useRef<any>(null);
  const [editInstruction, setEditInstruction] = useState('');
  const [lineTarget, setLineTarget] = useState('');

  const runInlineEdit = () => {
    const editor = editorRef.current;
    const model = editor?.getModel?.();
    if (!editor || !model || !file) return;
    const selection = editor.getSelection();
    const start = model.getOffsetAt(selection.getStartPosition());
    const end = model.getOffsetAt(selection.getEndPosition());
    const selectedText = file.content.slice(start, end);
    onInlineEdit(editInstruction, selectedText, start, end);
  };

  const runCompletion = () => {
    const editor = editorRef.current;
    const model = editor?.getModel?.();
    if (!editor || !model || !file) return;
    onComplete(model.getOffsetAt(editor.getPosition()));
  };

  const goToLine = () => {
    const editor = editorRef.current;
    const line = Number.parseInt(lineTarget, 10);
    if (!editor || !Number.isFinite(line) || line < 1) return;
    editor.revealLineInCenter(line);
    editor.setPosition({ lineNumber: line, column: 1 });
    editor.focus();
  };

  const formatDocument = async () => {
    const editor = editorRef.current;
    if (!editor) return;
    await editor.getAction('editor.action.formatDocument')?.run();
  };

  return (
    <section className={styles.editor}>
      <div className={styles.panelHeader}>
        <span className={styles.editorTitle}><Code2 size={15} /> {file ? file.filename : 'Editor'}</span>
        {file && <span className={styles.meta}>{languageLabel(file.filename)}{file.dirty ? ' - unsaved' : ''}</span>}
        {onToggleExpand && (
          <button
            className={styles.editorCollapseButton}
            type="button"
            onClick={onToggleExpand}
            title={isCollapsed ? 'Expand Editor' : 'Close Editor'}
          >
            {isCollapsed ? <Maximize2 size={14} /> : <Minimize2 size={14} />}
          </button>
        )}
      </div>
      {tabs.length > 0 && (
        <div className={styles.editorTabs}>
          {tabs.map((tab) => (
            <div
              key={tab.id}
              className={tab.id === activeFileId ? styles.editorTabActive : styles.editorTab}
              title={tab.filename}
            >
              <button type="button" onClick={() => onSelectTab(tab.id)}>
                <span>{tab.filename}</span>
              </button>
              {tab.dirty && <strong aria-label="Unsaved changes" />}
              <button
                type="button"
                onClick={() => onCloseTab(tab.id)}
                aria-label={`Close ${tab.filename}`}
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
      {file ? (
        <>
          <div className={styles.editorToolbar}>
            <button className={styles.editorToolButton} type="button" onClick={formatDocument} disabled={busy}>
              <Braces size={14} /> Format
            </button>
            <div className={styles.goToLine}>
              <input
                value={lineTarget}
                onChange={(event) => setLineTarget(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') goToLine();
                }}
                inputMode="numeric"
                placeholder="Line"
              />
              <button type="button" onClick={goToLine}>Go</button>
            </div>
          </div>
          <div className={styles.monacoShell}>
            <MonacoEditor
              path={file.filename}
              language={monacoLanguage(file.filename)}
              theme="vs-dark"
              value={file.content}
              onMount={(editor) => {
                editorRef.current = editor;
                editor.focus();
              }}
              onChange={(value) => onChange(value || '')}
              options={{
                automaticLayout: true,
                fontFamily: 'var(--font-mono), Consolas, monospace',
                fontSize: 13,
                lineHeight: 21,
                minimap: { enabled: true },
                scrollBeyondLastLine: false,
                smoothScrolling: true,
                tabSize: 2,
                wordWrap: 'off',
                renderWhitespace: 'selection',
                bracketPairColorization: { enabled: true },
                guides: { bracketPairs: true, indentation: true },
                padding: { top: 12, bottom: 12 },
              }}
            />
          </div>
          <div className={styles.inlineEditBar}>
            <input
              className={styles.inlineEditInput}
              value={editInstruction}
              onChange={(event) => setEditInstruction(event.target.value)}
              placeholder="Select code, then ask NEXUS to edit it..."
            />
            <button className={styles.fullWidthButton} type="button" onClick={runInlineEdit} disabled={busy || !editInstruction.trim()}>
              <Wand2 size={14} /> AI Edit
            </button>
            <button className={styles.fullWidthButton} type="button" onClick={runCompletion} disabled={busy}>
              Complete
            </button>
          </div>
          <div className={styles.editorFooter}>
            <span className={styles.meta}>{file.content.split('\n').length} lines</span>
            <button className={styles.sendButton} type="button" onClick={onSave} disabled={busy || !file.dirty}>
              <Save size={16} /> Save
            </button>
          </div>
        </>
      ) : (
        <div className={styles.emptyState}>
          <div>
            <h1>Open a file</h1>
            <p>Select a workspace file to inspect and edit it before asking NEXUS to plan or patch.</p>
          </div>
        </div>
      )}
    </section>
  );
}
