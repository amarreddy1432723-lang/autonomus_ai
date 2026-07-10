'use client';

import { ArrowRight, CheckCircle2, FileText, ListChecks } from 'lucide-react';
import type { WorkspaceSuggestion } from './workspaceSuggestions';
import styles from './Workspace.module.css';

type Props = {
  suggestions: WorkspaceSuggestion[];
  activeSuggestionId?: string;
  onTypeSuggestion: (suggestion: WorkspaceSuggestion) => void;
  busy: boolean;
};

export default function WorkspaceTaskPanel({ suggestions, activeSuggestionId, onTypeSuggestion, busy }: Props) {
  return (
    <aside className={styles.taskPanel}>
      <div className={styles.panelHeader}>
        <span>Suggested Tasks</span>
        <ListChecks size={13} />
      </div>
      <div className={styles.taskList}>
        <div className={styles.taskIntro}>
          <strong>Choose the next move. Nothing runs until you send it.</strong>
          <span>NEXUS converts vague descriptions into clear paths so you spend less time deciding what to ask.</span>
        </div>
        {suggestions.length === 0 && (
          <div className={styles.taskEmpty}>
            <strong>Describe what you want in the composer.</strong>
            <span>Three task options will appear here with planned files, impact, and checks.</span>
          </div>
        )}
        {suggestions.map((suggestion, index) => (
          <article
            className={activeSuggestionId === suggestion.id ? styles.taskCardActive : styles.taskCard}
            key={suggestion.id}
          >
            <div className={styles.taskCardHeader}>
              <span>{index + 1}</span>
              <div>
                <strong>{suggestion.title}</strong>
                <em>{suggestion.mode}</em>
              </div>
            </div>
            <p>{suggestion.summary}</p>
            <div className={styles.taskMetaLine}>
              <FileText size={12} />
              <span>{suggestion.fileHint}</span>
            </div>
            <div className={styles.taskMetaLine}>
              <CheckCircle2 size={12} />
              <span>{suggestion.checkHint}</span>
            </div>
            <div className={styles.taskImpact}>{suggestion.impact}</div>
            <button type="button" onClick={() => onTypeSuggestion(suggestion)} disabled={busy}>
              Type this prompt
              <ArrowRight size={12} />
            </button>
          </article>
        ))}
      </div>
    </aside>
  );
}
