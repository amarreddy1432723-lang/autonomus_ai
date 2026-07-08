'use client';

import { Save } from 'lucide-react';
import { useRef, useState } from 'react';
import styles from './Workspace.module.css';

export type OpenWorkspaceFile = {
  id: string;
  filename: string;
  content: string;
  dirty: boolean;
};

type Props = {
  file: OpenWorkspaceFile | null;
  busy: boolean;
  onChange: (content: string) => void;
  onSave: () => void;
  onInlineEdit: (instruction: string, selectedText: string, start: number, end: number) => void;
  onComplete: (cursor: number) => void;
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

export default function EditorPanel({ file, busy, onChange, onSave, onInlineEdit, onComplete }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [editInstruction, setEditInstruction] = useState('');

  const runInlineEdit = () => {
    const textarea = textareaRef.current;
    if (!textarea || !file) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = file.content.slice(start, end);
    onInlineEdit(editInstruction, selectedText, start, end);
  };

  const runCompletion = () => {
    const textarea = textareaRef.current;
    if (!textarea || !file) return;
    onComplete(textarea.selectionStart);
  };

  return (
    <section className={styles.editor}>
      <div className={styles.panelHeader}>
        <span>{file ? file.filename : 'Editor'}</span>
        {file && <span className={styles.meta}>{languageLabel(file.filename)}{file.dirty ? ' - unsaved' : ''}</span>}
      </div>
      {file ? (
        <>
          <textarea
            ref={textareaRef}
            className={styles.codeEditor}
            spellCheck={false}
            value={file.content}
            onChange={(event) => onChange(event.target.value)}
          />
          <div className={styles.inlineEditBar}>
            <input
              className={styles.inlineEditInput}
              value={editInstruction}
              onChange={(event) => setEditInstruction(event.target.value)}
              placeholder="Select code, then ask NEXUS to edit it..."
            />
            <button className={styles.fullWidthButton} type="button" onClick={runInlineEdit} disabled={busy || !editInstruction.trim()}>
              AI Edit
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
