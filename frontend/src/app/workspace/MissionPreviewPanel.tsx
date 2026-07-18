'use client';

import { AlertTriangle, CheckCircle2, GitBranch, ListChecks, Network, ShieldQuestion } from 'lucide-react';
import styles from './Workspace.module.css';

export type CompiledMissionPreview = {
  state: 'COMPILED' | 'CLARIFICATION_REQUIRED' | string;
  intent?: {
    execution_allowed?: boolean;
    risk_level?: string;
    unknowns?: string[];
    deliverables?: string[];
  };
  definition?: {
    title?: string;
    objective?: string;
    unknowns?: string[];
    required_capabilities?: string[];
    success_criteria?: string[];
    risk_profile?: {
      level?: string;
      categories?: string[];
      reasons?: string[];
      clarification_required?: boolean;
    };
    execution_graph?: {
      nodes?: Array<{ node_id: string; node_type: string; title: string; status?: string }>;
      edges?: Array<{ source_id: string; target_id: string; edge_type: string }>;
    };
  };
  aml?: any;
};

type Props = {
  preview: CompiledMissionPreview | null;
  busy: boolean;
  onClear: () => void;
  onContinue: () => void;
};

function titleCase(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function MissionPreviewPanel({ preview, busy, onClear, onContinue }: Props) {
  if (!preview) return null;
  const definition = preview.definition || {};
  const risk = definition.risk_profile?.level || preview.intent?.risk_level || 'unknown';
  const capabilities = (definition.required_capabilities || []).slice(0, 8);
  const unknowns = definition.unknowns || preview.intent?.unknowns || [];
  const nodes = definition.execution_graph?.nodes || [];
  const verificationNodes = nodes.filter((node) => node.node_type === 'verification' || node.node_type === 'review' || node.node_type === 'approval');
  const blocked = preview.state === 'CLARIFICATION_REQUIRED';

  return (
    <section className={styles.missionPreviewPanel} aria-label="Compiled mission preview">
      <div className={styles.missionPreviewHeader}>
        <div>
          <span className={blocked ? styles.missionPreviewWarn : styles.missionPreviewOk}>
            {blocked ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
            {blocked ? 'Clarification required' : 'Mission compiled'}
          </span>
          <strong>{definition.title || 'Compiled mission'}</strong>
          <p>{definition.objective || 'Arceus compiled the request into AML and an execution graph.'}</p>
        </div>
        <button type="button" onClick={onClear} disabled={busy}>Dismiss</button>
      </div>

      <div className={styles.missionPreviewStats}>
        <span><ShieldQuestion size={13} /> Risk: {titleCase(risk)}</span>
        <span><ListChecks size={13} /> {capabilities.length} capabilities</span>
        <span><GitBranch size={13} /> {nodes.length} graph nodes</span>
        <span><Network size={13} /> AML v{preview.aml?.version || '1.0'}</span>
      </div>

      {unknowns.length > 0 && (
        <div className={styles.missionPreviewQuestions}>
          <strong>Questions before execution</strong>
          {unknowns.map((item) => <span key={item}>{item}</span>)}
        </div>
      )}

      <div className={styles.missionPreviewGrid}>
        <div>
          <strong>Required capabilities</strong>
          <div className={styles.missionPreviewPills}>
            {capabilities.map((capability) => <span key={capability}>{titleCase(capability)}</span>)}
          </div>
        </div>
        <div>
          <strong>Execution graph</strong>
          <div className={styles.missionPreviewGraph}>
            {nodes.slice(0, 7).map((node, index) => (
              <span key={node.node_id}>
                {index > 0 && <em>→</em>}
                {titleCase(node.node_type)}
              </span>
            ))}
          </div>
        </div>
      </div>

      <details className={styles.missionPreviewDetails}>
        <summary>View AML</summary>
        <pre>{JSON.stringify(preview.aml || {}, null, 2)}</pre>
      </details>

      <div className={styles.missionPreviewFooter}>
        <span>{blocked ? 'Answer the questions above before Arceus executes tools.' : `${verificationNodes.length} review or verification gate(s) are planned before completion.`}</span>
        <button type="button" onClick={onContinue} disabled={busy || blocked}>
          Approve Plan Path
        </button>
      </div>
    </section>
  );
}

