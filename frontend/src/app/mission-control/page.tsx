'use client';

import { Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Bell,
  Check,
  Cloud,
  GitBranch,
  Pause,
  Rocket,
  Search,
  ShieldCheck,
  UserRound,
} from 'lucide-react';
import styles from './MissionControl.module.css';

const ENGINEERS = [
  ['EM', 'Engineering Manager', 'Coordinating sprint execution', '98%', '4 files', 'Ready', '12m'],
  ['AR', 'Architect', 'Reviewing API boundaries', '96%', '2 docs', 'Reviewing', '18m'],
  ['FE', 'Frontend', 'Building login workflow', '94%', '8 files', 'Active', '24m'],
  ['BE', 'Backend', 'Implementing authentication API', '91%', '6 files', 'Active', '19m'],
  ['DB', 'Database', 'Preparing migration plan', '95%', '3 files', 'Waiting', '16m'],
  ['AI', 'AI', 'Routing model workers', '93%', '5 files', 'Active', '21m'],
  ['QA', 'QA', 'Generating regression tests', '92%', '12 tests', 'Active', '28m'],
  ['SE', 'Security', 'Checking OAuth configuration', '89%', '1 issue', 'Attention', '9m'],
  ['DO', 'DevOps', 'Preparing preview deployment', '94%', '2 files', 'Queued', '31m'],
  ['DE', 'Docs', 'Updating implementation notes', '97%', '3 docs', 'Ready', '22m'],
];

const SPRINT = [
  ['Current Milestone', 'Core Platform', 'Engineering Manager', 'P0', 'None', '10 weeks plan', '18%'],
  ['Completed', 'Project foundation', 'DevOps', 'P0', 'Stack approved', 'Done', '100%'],
  ['In Progress', 'Authentication module', 'Backend', 'P0', 'API contracts', '34m', '65%'],
  ['Waiting Review', 'Database schema', 'Database', 'P1', 'Security check', '12m', '82%'],
  ['Blocked', 'OAuth provider settings', 'Security', 'P0', 'Clerk keys', 'Needs input', '44%'],
  ['Upcoming', 'Frontend login UI', 'Frontend', 'P1', 'Auth API', '48m', '0%'],
];

const ARTIFACTS = [
  ['Repository', 'Connected', 'Updated 2m ago'],
  ['Architecture Documents', 'Current', 'Approved'],
  ['API Specification', 'Reviewing', '12 endpoints'],
  ['Database Schema', 'Draft ready', '6 tables'],
  ['UI Components', 'Building', '9 components'],
  ['Test Reports', 'Running', '42 tests'],
  ['Security Reports', 'Attention', '1 warning'],
  ['Deployment Pipeline', 'Queued', 'Preview next'],
];

const CONTROLS = [
  ['Approval Queue', '3 waiting', 'Review important decisions'],
  ['Pull Requests', '0 open', 'Approved changes only'],
  ['Architecture Decisions', '2 pending', 'API and schema'],
  ['Security Warnings', '1 active', 'OAuth configuration'],
  ['Deployment Readiness', '72%', 'Preview nearly ready'],
  ['Budget', 'Within limit', '$18.40 used'],
  ['Token Usage', 'Healthy', '14% monthly'],
  ['Infrastructure Cost', '$7.20', 'Projected today'],
  ['Build Health', 'Passing', 'Last check green'],
];

const ACTIVITY = [
  ['09:21', 'Frontend Engineer completed Login UI draft.'],
  ['09:24', 'Backend Engineer finished Authentication API contract.'],
  ['09:27', 'QA generated 42 unit tests.'],
  ['09:30', 'Security Engineer detected OAuth configuration issue.'],
  ['09:33', 'DevOps deployed Preview Environment plan.'],
];

const STATUS = [
  ['Repository', 'Healthy'],
  ['Tests', 'Passing'],
  ['Security Score', '99'],
  ['Deployment', 'Ready soon'],
  ['Branch', 'arceus/sprint-1'],
  ['AI Models', 'Healthy'],
];

function MissionControlPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const idea = searchParams.get('idea') || '';
  const stack = searchParams.get('stack') || 'recommended';

  const openWorkspace = () => {
    const params = new URLSearchParams();
    params.set('stage', 'workspace');
    params.set('stack', stack);
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/workspace?${params.toString()}`);
  };

  const openEvolutionCenter = () => {
    const params = new URLSearchParams();
    params.set('stage', 'evolution');
    params.set('stack', stack);
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/evolution-center?${params.toString()}`);
  };

  return (
    <main className={styles.operations}>
      <section className={styles.window} aria-label="Arceus Code engineering operations center">
        <header className={styles.topbar}>
          <div className={styles.brand}>
            <span>A</span>
            <div>
              <strong>Arceus Code</strong>
              <small>Healthcare AI Platform</small>
            </div>
          </div>
          <div className={styles.sprintMeta}>
            <span>Current Sprint <b>Sprint 1</b></span>
            <span>Overall Progress <b>18%</b></span>
            <i><em style={{ width: '18%' }} /></i>
          </div>
          <label className={styles.search}>
            <Search size={17} />
            <input aria-label="Search everything" placeholder="Search everything..." />
          </label>
          <div className={styles.actions}>
            <button type="button" aria-label="Notifications"><Bell size={18} /></button>
            <button type="button" aria-label="Profile"><UserRound size={18} /></button>
            <span><Cloud size={15} /> Synced</span>
          </div>
        </header>

        <section className={styles.hero}>
          <p><span /> 10 Engineers Active</p>
          <h1>Engineering Operations Center</h1>
          <strong>Your AI engineering organization is building your product.</strong>
        </section>

        <section className={styles.grid}>
          <article className={styles.panel}>
            <header><h2>Engineering Organization</h2><small>Autonomous team hierarchy</small></header>
            <div className={styles.orgList}>
              {ENGINEERS.map(([initials, role, task, confidence, files, state, eta], index) => (
                <button type="button" key={role} className={styles.engineer} data-state={state.toLowerCase()} style={{ animationDelay: `${index * 45}ms` }}>
                  <span>{initials}</span>
                  <div>
                    <strong>{role}</strong>
                    <small>{task}</small>
                    <em>{confidence} confidence · {files} · ETA {eta}</em>
                  </div>
                  <b>{state}</b>
                </button>
              ))}
            </div>
          </article>

          <article className={styles.panel}>
            <header><h2>Current Sprint</h2><small>Execution board, not a task dump</small></header>
            <div className={styles.sprintBoard}>
              {SPRINT.map(([section, title, owner, priority, dependencies, eta, progress]) => (
                <section key={`${section}-${title}`} className={styles.taskCard}>
                  <div>
                    <span>{section}</span>
                    <b>{priority}</b>
                  </div>
                  <h3>{title}</h3>
                  <p>{owner} · {dependencies}</p>
                  <footer>
                    <small>{eta}</small>
                    <strong>{progress}</strong>
                  </footer>
                  <i><em style={{ width: progress }} /></i>
                </section>
              ))}
            </div>
          </article>

          <article className={styles.panel}>
            <header><h2>Artifacts</h2><small>Live engineering outputs</small></header>
            <div className={styles.artifactList}>
              {ARTIFACTS.map(([name, state, detail]) => (
                <button type="button" key={name} className={styles.artifact}>
                  <span><GitBranch size={15} /></span>
                  <div>
                    <strong>{name}</strong>
                    <small>{detail}</small>
                  </div>
                  <b>{state}</b>
                </button>
              ))}
            </div>
          </article>

          <article className={styles.panel}>
            <header><h2>Executive Control</h2><small>Founder-level decisions</small></header>
            <div className={styles.controlList}>
              {CONTROLS.map(([name, value, detail]) => (
                <button type="button" key={name} className={styles.control}>
                  <div>
                    <strong>{name}</strong>
                    <small>{detail}</small>
                  </div>
                  <b>{value}</b>
                </button>
              ))}
            </div>
          </article>
        </section>

        <section className={styles.activity}>
          <header>
            <div>
              <h2>Activity Timeline</h2>
              <small>Live engineering feed without noisy logs.</small>
            </div>
            <div className={styles.primaryActions}>
              <button type="button"><Pause size={16} /> Pause Engineering</button>
              <button type="button"><ShieldCheck size={16} /> Review Decisions</button>
              <button type="button" onClick={openWorkspace}>Open Workspace</button>
              <button type="button" onClick={openEvolutionCenter}><Rocket size={16} /> Deploy Preview</button>
            </div>
          </header>
          <div className={styles.feed}>
            {ACTIVITY.map(([time, text]) => (
              <article key={`${time}-${text}`}>
                <b>{time}</b>
                <span>{text}</span>
              </article>
            ))}
          </div>
        </section>

        <footer className={styles.statusBar}>
          {STATUS.map(([label, value]) => (
            <span key={label}><Check size={13} /><b>{label}</b>{value}</span>
          ))}
        </footer>
      </section>
    </main>
  );
}

export default function MissionControlPage() {
  return (
    <Suspense fallback={null}>
      <MissionControlPageContent />
    </Suspense>
  );
}
