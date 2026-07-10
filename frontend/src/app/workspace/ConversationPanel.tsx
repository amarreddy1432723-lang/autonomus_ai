'use client';

import { Bot, ChevronDown, Code2, Layers, Mic, Paperclip, Plus, X, ArrowUp } from 'lucide-react';
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
      <div className={styles.agentHeader}>
        <div className={styles.agentTitle}>
          <Bot size={15} />
          <span>New Agent</span>
        </div>
        <div className={styles.agentHeaderActions}>
          <button type="button" title="New agent" disabled={busy}>
            <Plus size={14} />
          </button>
          <button type="button" title="Close agent panel">
            <X size={14} />
          </button>
        </div>
      </div>
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
              <span className={styles.messageAvatar}>{message.role === 'user' ? 'U' : 'N'}</span>
              <div className={styles.messageContent}>{message.content}</div>
            </article>
          ))
        )}
      </div>
      <div className={styles.composer}>
        <div className={styles.prolongedComposer}>
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
            placeholder="Plan, Build, / for skills, @ for context"
            rows={1}
          />
          <div className={styles.agentToolbar}>
            <div className={styles.agentModeSelect}>
              <Code2 size={13} />
              <select value={mode} onChange={(event) => onModeChange(event.target.value as WorkspaceMode)} disabled={busy} title="Agent mode">
                {modes.map((item) => (
                  <option key={item.id} value={item.id}>{item.label}</option>
                ))}
              </select>
              <ChevronDown size={12} />
            </div>
            <select className={styles.modelSelect} defaultValue="composer-2.5-fast" title="Agent model">
              <option value="composer-2.5-fast">Composer 2.5 Fast</option>
              <option value="nexus-agent-pro">NEXUS Agent Pro</option>
              <option value="autonomus-ai">Autonomus AI</option>
            </select>
            <span className={styles.contextCount}>{selectedFileCount} ctx</span>
          </div>
          <div className={styles.composerControlsRight}>
            <button className={styles.composerAttachBtn} type="button" onClick={onAttachClick} disabled={busy} title="Attach files">
              <Paperclip size={14} />
            </button>
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
