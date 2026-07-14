'use client';

import { ArrowUp, Bot, ChevronDown, Code2, Layers, Mic, Paperclip, Plus, X } from 'lucide-react';
import styles from './Workspace.module.css';
import WorkReceipt, { type WorkspaceWorkReceipt } from './WorkReceipt';
import type { WorkspaceSuggestion } from './workspaceSuggestions';

export type WorkspaceMode = 'auto' | 'code' | 'plan' | 'design' | 'deploy' | 'research';

export type WorkspaceMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  receipt?: WorkspaceWorkReceipt;
};

type Props = {
  mode: WorkspaceMode;
  messages: WorkspaceMessage[];
  prompt: string;
  busy: boolean;
  selectedFileCount: number;
  suggestions: WorkspaceSuggestion[];
  activeProjectName?: string;
  activeSessionLabel?: string;
  onModeChange: (mode: WorkspaceMode) => void;
  onPromptChange: (value: string) => void;
  onTypeSuggestion: (suggestion: WorkspaceSuggestion) => void;
  onSubmit: () => void;
  onSubmitBackground: () => void;
  onAttachClick: () => void;
  onOpenTool?: (tool: 'terminal' | 'changes' | 'jobs' | 'preview') => void;
  onOpenFile?: (filename: string) => void | Promise<void>;
  onRollback?: () => void | Promise<void>;
};

const modes: { id: WorkspaceMode; label: string }[] = [
  { id: 'auto', label: 'Auto' },
  { id: 'code', label: 'Code' },
  { id: 'plan', label: 'Plan' },
  { id: 'design', label: 'Design' },
  { id: 'deploy', label: 'Deploy' },
  { id: 'research', label: 'Research' },
];

function compactText(value: string, max = 180) {
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max - 1).trim()}...`;
}

function lineCount(value: string) {
  return value.split(/\r?\n/).filter((line) => line.trim()).length;
}

function wordCount(value: string) {
  return value.trim() ? value.trim().split(/\s+/).length : 0;
}

function extractFileMentions(value: string) {
  const matches = value.match(/(?:[\w.-]+\/)+[\w.-]+\.[a-zA-Z0-9]+|[\w.-]+\.(?:tsx|ts|jsx|js|py|css|html|json|md|yml|yaml|toml|env|txt)/g) || [];
  return Array.from(new Set(matches)).slice(0, 5);
}

function inferTaskType(value: string) {
  const text = value.toLowerCase();
  if (/(fix|bug|error|broken|not working|issue)/.test(text)) return 'Fix';
  if (/(design|ui|ux|layout|screen|component|style)/.test(text)) return 'Design';
  if (/(deploy|railway|vercel|production|release)/.test(text)) return 'Deploy';
  if (/(test|lint|typecheck|build|compile)/.test(text)) return 'Check';
  if (/(research|compare|latest|find|search)/.test(text)) return 'Research';
  return 'Build';
}

function parseAssistantContent(value: string) {
  const trimmed = value.trim();
  if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return null;
  try {
    const payload = JSON.parse(trimmed);
    if (!payload || typeof payload !== 'object') return null;
    return {
      status: typeof payload.status === 'string' ? payload.status : 'updated',
      outputType: typeof payload.output_type === 'string' ? payload.output_type : 'response',
      content: typeof payload.content === 'string' ? payload.content.trim() : '',
    };
  } catch {
    return null;
  }
}

function MessageBody({
  message,
  onTypeSuggestion,
  onOpenTool,
  onOpenFile,
  onRollback,
  busy,
}: {
  message: WorkspaceMessage;
  onTypeSuggestion: (suggestion: WorkspaceSuggestion) => void;
  onOpenTool?: (tool: 'terminal' | 'changes' | 'jobs' | 'preview') => void;
  onOpenFile?: (filename: string) => void | Promise<void>;
  onRollback?: () => void | Promise<void>;
  busy: boolean;
}) {
  const files = extractFileMentions(message.content);
  const parsed = message.role === 'assistant' ? parseAssistantContent(message.content) : null;
  const taskType = inferTaskType(message.content);
  const content = parsed ? parsed.content : message.content;
  const isLong = !message.receipt && (content.length > 260 || lineCount(content) > 5);
  const primary = parsed && !parsed.content
    ? 'Arceus prepared a structured draft. Open Changes or Jobs to inspect the generated files and execution state.'
    : content;

  return (
    <div className={styles.messageContent}>
      <div className={styles.messageHeaderRow}>
        <strong>{message.role === 'user' ? 'You' : 'Arceus Code'}</strong>
        <span>
          {message.role === 'user' ? `${taskType} request` : parsed ? `${parsed.status} · ${parsed.outputType}` : 'Agent response'}
        </span>
      </div>
      {message.role === 'user' && (
        <div className={styles.messageDecisionRow}>
          <span>{taskType}</span>
          <span>{wordCount(message.content)} words</span>
          <span>{lineCount(message.content)} lines</span>
          {files.length > 0 && <span>{files.length} file refs</span>}
        </div>
      )}
      {message.receipt ? (
        <WorkReceipt
          receipt={message.receipt}
          onTypeSuggestion={onTypeSuggestion}
          onOpenTool={onOpenTool}
          onOpenFile={onOpenFile}
          onRollback={onRollback}
          busy={busy}
        />
      ) : (
        <div className={isLong ? styles.messagePreview : styles.messageText}>
          {isLong ? compactText(primary, 260) : primary}
        </div>
      )}
      {message.receipt && primary.trim() && primary.trim() !== message.receipt.summary.trim() && (
        <details className={styles.messageDetails}>
          <summary>View explanation</summary>
          <pre>{primary}</pre>
        </details>
      )}
      {isLong && (
        <details className={styles.messageDetails}>
          <summary>{message.role === 'user' ? 'Show full prompt' : 'Show full response'}</summary>
          <pre>{primary}</pre>
        </details>
      )}
      {files.length > 0 && (
        <div className={styles.messageFiles}>
          {files.map((file) => <span key={file}>{file}</span>)}
        </div>
      )}
    </div>
  );
}

export default function ConversationPanel({
  mode,
  messages,
  prompt,
  busy,
  selectedFileCount,
  suggestions,
  activeProjectName,
  activeSessionLabel,
  onModeChange,
  onPromptChange,
  onTypeSuggestion,
  onSubmit,
  onSubmitBackground,
  onAttachClick,
  onOpenTool,
  onOpenFile,
  onRollback,
}: Props) {
  return (
    <section className={styles.conversation}>
      <div className={styles.agentHeader}>
        <div className={styles.agentTitle}>
          <Bot size={15} />
          <span>{activeProjectName ? `${activeProjectName} Agent` : 'New Agent'}</span>
          {activeSessionLabel && <em>{activeSessionLabel}</em>}
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
              <p>Open a folder or describe what you want to build. Arceus will suggest the next 3 actions before execution.</p>
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <article
              className={`${styles.message} ${message.role === 'user' ? styles.userMessage : styles.assistantMessage}`}
              key={message.id}
            >
              <span className={styles.messageAvatar}>{message.role === 'user' ? 'U' : 'A'}</span>
              <MessageBody
                message={message}
                onTypeSuggestion={onTypeSuggestion}
                onOpenTool={onOpenTool}
                onOpenFile={onOpenFile}
                onRollback={onRollback}
                busy={busy}
              />
            </article>
          ))
        )}
      </div>
      <div className={styles.composer}>
        {prompt.trim().length > 0 && suggestions.length > 0 && (
          <div className={styles.nextMoveStrip}>
            <div className={styles.nextMoveHeader}>
              <span>Arceus suggests</span>
              <em>Pick a direction before execution</em>
            </div>
            <div className={styles.nextMoveGrid}>
              {suggestions.map((suggestion) => (
                <article className={styles.nextMoveCard} key={suggestion.id}>
                  <div>
                    <strong>{suggestion.title}</strong>
                    <span>{suggestion.summary}</span>
                  </div>
                  <button type="button" onClick={() => onTypeSuggestion(suggestion)} disabled={busy}>
                    Type
                  </button>
                </article>
              ))}
            </div>
          </div>
        )}
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
            placeholder="Plan, build, debug, or ask anything. / for skills, @ for context"
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
              <option value="nexus-agent-pro">Arceus Agent Pro</option>
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
