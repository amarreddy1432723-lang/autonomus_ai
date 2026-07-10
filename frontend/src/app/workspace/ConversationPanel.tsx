'use client';

import { Paperclip, Send, Mic, ArrowUp, Layers } from 'lucide-react';
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
  onSubmitBackground: () => void;
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
  onSubmitBackground,
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
        <div className={styles.prolongedComposer}>
          <button className={styles.composerAttachBtn} type="button" onClick={onAttachClick} disabled={busy} title="Attach files">
            <Paperclip size={14} />
          </button>
          <textarea
            className={styles.prolongedInput}
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                onSubmit();
              }
            }}
            placeholder="Message NEXUS Code..."
            rows={1}
          />
          <div className={styles.composerControlsRight}>
            <button className={styles.composerMicBtn} type="button" title="Voice Assist">
              <Mic size={14} />
            </button>
            <button className={styles.composerBgBtn} type="button" onClick={onSubmitBackground} disabled={busy || !prompt.trim()} title="Execute in Background">
              <Layers size={13} />
            </button>
            <button className={styles.composerSendBtn} type="button" onClick={onSubmit} disabled={busy || !prompt.trim()} title="Send message">
              <ArrowUp size={14} />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
