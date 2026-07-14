'use client';

import { CheckCircle2, GitBranch, Network, RefreshCw, Send, ShieldCheck, Wand2 } from 'lucide-react';
import styles from './Workspace.module.css';

export type EngineeringProposal = {
  id: string;
  perspective: string;
  title: string;
  summary: string;
  architecture: string;
  advantages: string[];
  disadvantages: string[];
  estimated_cost: string;
  estimated_complexity: string;
  risks: string[];
  recommended_for: string;
  score: number;
  judge_summary: string;
};

export type EngineeringOrgState = {
  id?: string;
  stage?: string;
  original_problem?: string;
  clarified_problem?: string;
  selected_proposal_id?: string | null;
  architecture_document?: Record<string, any>;
  implementation_plan?: Record<string, any>;
  tasks?: Array<Record<string, any>>;
  proposals?: EngineeringProposal[];
  decisions?: Array<Record<string, any>>;
};

type Props = {
  projectName?: string;
  state: EngineeringOrgState | null;
  problem: string;
  busy?: boolean;
  onProblemChange: (value: string) => void;
  onAnalyze: () => void;
  onRefresh: () => void;
  onSelectProposal: (proposalId: string) => void;
  onApproveArchitecture: () => void;
  onMaterializeTasks: () => void;
  onTypeTask: (taskId: string) => void;
};

function stageLabel(stage?: string) {
  return (stage || 'intake').replace(/_/g, ' ');
}

export default function EngineeringOrgPanel({
  projectName,
  state,
  problem,
  busy,
  onProblemChange,
  onAnalyze,
  onRefresh,
  onSelectProposal,
  onApproveArchitecture,
  onMaterializeTasks,
  onTypeTask,
}: Props) {
  const proposals = state?.proposals || [];
  const selectedId = state?.selected_proposal_id;
  const architecture = state?.architecture_document || {};
  const tasks = state?.tasks || [];

  return (
    <aside className={styles.rightExplorerPanel}>
      <div className={styles.rightDrawerHeader}>
        <span>Engineering Org</span>
        <button type="button" onClick={onRefresh} disabled={busy} title="Refresh engineering organization">
          <RefreshCw size={13} />
          Refresh
        </button>
      </div>

      <section className={styles.appsPanelSection}>
        <div className={styles.panelTitleRow}>
          <Network size={14} />
          <div>
            <strong>{projectName || 'Active project'}</strong>
            <small>Stage: {stageLabel(state?.stage)}</small>
          </div>
        </div>
        <textarea
          className={styles.commandTextarea}
          value={problem}
          onChange={(event) => onProblemChange(event.target.value)}
          placeholder="Describe the product or feature. Arceus will generate three senior engineering proposals."
          rows={5}
          disabled={busy}
        />
        <button className={styles.commandButtonPrimary} type="button" onClick={onAnalyze} disabled={busy || problem.trim().length < 3}>
          <Send size={13} />
          Generate 3 proposals
        </button>
      </section>

      {proposals.length > 0 && (
        <section className={styles.appsPanelSection}>
          <div className={styles.panelTitleRow}>
            <GitBranch size={14} />
            <div>
              <strong>Three senior proposals</strong>
              <small>Recommended option is scored highest by the judge.</small>
            </div>
          </div>
          {proposals.map((proposal) => {
            const selected = selectedId === proposal.id;
            return (
              <article className={selected ? styles.proposalCardSelected : styles.proposalCard} key={proposal.id}>
                <header>
                  <span>{proposal.perspective}</span>
                  <strong>{proposal.score}%</strong>
                </header>
                <h4>{proposal.title}</h4>
                <p>{proposal.summary}</p>
                <small>{proposal.judge_summary}</small>
                <div className={styles.proposalMeta}>
                  <em>Cost: {proposal.estimated_cost}</em>
                  <em>Complexity: {proposal.estimated_complexity}</em>
                </div>
                <details>
                  <summary>Architecture and risks</summary>
                  <pre>{proposal.architecture}</pre>
                  <ul>
                    {proposal.risks.map((risk) => <li key={risk}>{risk}</li>)}
                  </ul>
                </details>
                <button type="button" onClick={() => onSelectProposal(proposal.id)} disabled={busy || selected}>
                  {selected ? 'Selected' : 'Select proposal'}
                </button>
              </article>
            );
          })}
        </section>
      )}

      {selectedId && (
        <section className={styles.appsPanelSection}>
          <div className={styles.panelTitleRow}>
            <ShieldCheck size={14} />
            <div>
              <strong>Architecture and task graph</strong>
              <small>{architecture?.approval?.approved ? 'Approved' : 'Waiting for architecture approval'}</small>
            </div>
          </div>
          <div className={styles.orgArchitecture}>
            {(architecture.components || []).map((component: string) => <span key={component}>{component}</span>)}
          </div>
          {!architecture?.approval?.approved && (
            <button className={styles.commandButtonPrimary} type="button" onClick={onApproveArchitecture} disabled={busy}>
              <CheckCircle2 size={13} />
              Approve architecture
            </button>
          )}
          {architecture?.approval?.approved && (
            <button className={styles.commandButtonPrimary} type="button" onClick={onMaterializeTasks} disabled={busy || tasks.length === 0}>
              <Wand2 size={13} />
              Sync task rail
            </button>
          )}
          <div className={styles.orgTaskList}>
            {tasks.map((task) => (
              <div key={task.id || task.title}>
                <header>
                  <strong>{task.id}. {task.title}</strong>
                  <button
                    type="button"
                    onClick={() => onTypeTask(String(task.id))}
                    disabled={busy || task.status === 'blocked'}
                    title={task.status === 'blocked' ? 'Complete prerequisite tasks first' : 'Type this task into the composer'}
                  >
                    Type
                  </button>
                </header>
                <small>{task.assigned_role} · {task.workspace_status || task.status} · depends on {(task.depends_on || []).join(', ') || 'none'}</small>
                {!!task.suggested_prompt && <em>Prompt ready</em>}
              </div>
            ))}
          </div>
        </section>
      )}
    </aside>
  );
}
