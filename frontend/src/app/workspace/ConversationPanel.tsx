'use client';

import { Paperclip, Send } from 'lucide-react';
import styles from './Workspace.module.css';

export type WorkspaceMode = 'auto' | 'code' | 'plan' | 'design' | 'deploy' | 'research';

export type WorkspaceMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
};

type Props = {
  mode: WorkspaceMode;
  messages: WorkspaceMessage[];
  prompt: string;
  busy: boolean;
  selectedFileCount: number;
  onModeChange: (mode: WorkspaceMode) => void;
  onPromptChange: (value: string) => void;
  onSubmit: () => void;
  onAttachClick: () => void;
};

const modes: { id: WorkspaceMode; label: string }[] = [
  { id: 'auto', label: 'Auto' },
  { id: 'code', label: 'Code' },
  { id: 'plan', label: 'Plan' },
  { id: 'design', label: 'Design' },
  { id: 'deploy', label: 'Deploy' },
  { id: 'research', label: 'Research' },
];

export default function ConversationPanel({
  mode,
  messages,
  prompt,
  busy,
  selectedFileCount,
  onModeChange,
  onPromptChange,
  onSubmit,
  onAttachClick,
}: Props) {
  return (
    <section className={styles.conversation}>
      <div className={styles.messages}>
        {messages.length === 0 ? (
          <div className={styles.emptyState}>
            <div>
              <h1>What would you like to build or fix?</h1>
              <p>NEXUS Code can read files, plan, code, design, research, and prepare deployment from one prompt.</p>
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <article
              className={`${styles.message} ${message.role === 'user' ? styles.userMessage : styles.assistantMessage}`}
              key={message.id}
            >
              {message.content}
            </article>
          ))
        )}
      </div>
      <div className={styles.composer}>
        <div className={styles.modeRow}>
          {modes.map((item) => (
            <button
              key={item.id}
              className={`${styles.modePill} ${mode === item.id ? styles.modePillActive : ''}`}
              type="button"
              onClick={() => onModeChange(item.id)}
              disabled={busy}
            >
              {item.label}
            </button>
          ))}
          <span className={styles.meta}>{selectedFileCount} file{selectedFileCount === 1 ? '' : 's'} in context</span>
        </div>
        <div className={styles.inputRow}>
          <button className={styles.iconButton} type="button" onClick={onAttachClick} disabled={busy} aria-label="Attach files">
            <Paperclip size={16} />
          </button>
          <textarea
            className={styles.prompt}
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                event.preventDefault();
                onSubmit();
              }
            }}
            placeholder="Ask anything, attach files, build, deploy, research..."
          />
          <button className={styles.sendButton} type="button" onClick={onSubmit} disabled={busy || !prompt.trim()}>
            <Send size={16} /> {busy ? 'Working' : 'Send'}
          </button>
        </div>
      </div>
    </section>
  );
}
