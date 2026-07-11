'use client';

import { ArrowRight, CheckCircle2, FileText, Lightbulb, ListChecks, Scale } from 'lucide-react';
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
        {suggestions.map((suggestion, index) => {
          const confidence = typeof suggestion.confidence === 'number'
            ? `${Math.round(suggestion.confidence * 100)}%`
            : 'guided';
          return (
            <article
              className={activeSuggestionId === suggestion.id ? styles.taskCardActive : styles.taskCard}
              key={suggestion.id}
            >
              <div className={styles.taskCardHeader}>
                <span>{index + 1}</span>
                <div>
                  <strong>{suggestion.title}</strong>
                  <em>{suggestion.mode} · {suggestion.risk || 'medium'} · {confidence}{suggestion.requiresApproval ? ' · approval' : ''}</em>
                </div>
              </div>
              {!!suggestion.coachLens?.length && (
                <div className={styles.taskLensRow}>
                  {suggestion.coachLens.slice(0, 4).map((lens) => (
                    <span key={lens}>{lens}</span>
                  ))}
                </div>
              )}
              <p>{suggestion.summary}</p>
              {!!suggestion.decisionReason && (
                <div className={styles.taskCoach}>
                  <Lightbulb size={12} />
                  <span>{suggestion.decisionReason}</span>
                </div>
              )}
              {!!suggestion.steps?.length && (
                <ol className={styles.taskSteps}>
                  {suggestion.steps.slice(0, 3).map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              )}
              <div className={styles.taskMetaLine}>
                <FileText size={12} />
                <span>{suggestion.files?.length ? suggestion.files.slice(0, 4).join(', ') : suggestion.fileHint}</span>
              </div>
              <div className={styles.taskMetaLine}>
                <CheckCircle2 size={12} />
                <span>{suggestion.expectedCommands?.length ? suggestion.expectedCommands.slice(0, 3).join(', ') : suggestion.checkHint}</span>
              </div>
              {!!suggestion.tradeoffs?.length && (
                <div className={styles.taskTradeoffs}>
                  <Scale size={12} />
                  <span>{suggestion.tradeoffs.slice(0, 2).join(' ')}</span>
                </div>
              )}
              <div className={styles.taskImpact}>{suggestion.impact}</div>
              {!!suggestion.thinkingPrompt && (
                <div className={styles.taskThinking}>{suggestion.thinkingPrompt}</div>
              )}
              {!!suggestion.nextAfterDone && (
                <div className={styles.taskNext}>Next: {suggestion.nextAfterDone}</div>
              )}
              <button type="button" onClick={() => onTypeSuggestion(suggestion)} disabled={busy}>
                Type this prompt
                <ArrowRight size={12} />
              </button>
            </article>
          );
        })}
      </div>
    </aside>
  );
}
