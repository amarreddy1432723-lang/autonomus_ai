'use client';

import {
  Activity,
  Bell,
  Bot,
  BrainCircuit,
  CheckCircle2,
  CircleDot,
  Clock3,
  Command,
  Database,
  FlaskConical,
  FolderGit2,
  GitPullRequest,
  Home,
  LineChart,
  Network,
  Rocket,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Terminal,
  TestTube2,
  Workflow,
  Zap,
} from 'lucide-react';
import { motion } from 'framer-motion';
import { useMemo, useState } from 'react';
import styles from './ArceusMissionWorkspace.module.css';

type StatusTone = 'running' | 'complete' | 'waiting' | 'blocked' | 'thinking';

type Specialist = {
  role: string;
  task: string;
  progress: number;
  confidence: number;
  tone: StatusTone;
  update: string;
};

type ActivityItem = {
  time: string;
  actor: string;
  text: string;
  tone: StatusTone;
};

const sidebarItems = [
  { label: 'Workspace', icon: Home, active: true },
  { label: 'Missions', icon: CircleDot },
  { label: 'Organization', icon: Bot },
  { label: 'Repositories', icon: FolderGit2 },
  { label: 'Knowledge', icon: BrainCircuit },
  { label: 'Activity', icon: Activity },
  { label: 'Reviews', icon: ShieldCheck },
  { label: 'Deployments', icon: Rocket },
  { label: 'Automation', icon: Workflow },
  { label: 'Analytics', icon: LineChart },
  { label: 'Notifications', icon: Bell },
  { label: 'Settings', icon: Settings },
];

const specialists: Specialist[] = [
  { role: 'Mission Lead', task: 'Coordinating authentication modernization', progress: 68, confidence: 94, tone: 'thinking', update: '12 sec ago' },
  { role: 'Backend Engineer', task: 'Hardening session token refresh flow', progress: 74, confidence: 91, tone: 'running', update: '1 min ago' },
  { role: 'Frontend Engineer', task: 'Preparing account-state recovery UI', progress: 51, confidence: 88, tone: 'running', update: '2 min ago' },
  { role: 'Security Reviewer', task: 'Reviewing JWT and Redis session policy', progress: 42, confidence: 96, tone: 'thinking', update: 'Now' },
  { role: 'QA Engineer', task: 'Generating regression proof checks', progress: 37, confidence: 89, tone: 'waiting', update: '4 min ago' },
  { role: 'DevOps', task: 'Waiting for verification artifacts', progress: 18, confidence: 84, tone: 'waiting', update: '5 min ago' },
  { role: 'Documentation', task: 'Recording decisions and rollout notes', progress: 57, confidence: 93, tone: 'running', update: '3 min ago' },
];

const activity: ActivityItem[] = [
  { time: '09:20', actor: 'Backend', text: 'Completed OAuth callback analysis', tone: 'complete' },
  { time: '09:22', actor: 'QA', text: 'Started session recovery tests', tone: 'running' },
  { time: '09:24', actor: 'Security', text: 'Flagged missing production token boundary', tone: 'blocked' },
  { time: '09:25', actor: 'DevOps', text: 'Prepared deployment readiness checkpoint', tone: 'waiting' },
  { time: '09:27', actor: 'Docs', text: 'Updated mission evidence ledger', tone: 'complete' },
];

const bottomTabs = ['Terminal', 'Logs', 'Tasks', 'Runtime', 'Deployments', 'Tests'];

function toneLabel(tone: StatusTone) {
  if (tone === 'running') return 'Running';
  if (tone === 'complete') return 'Completed';
  if (tone === 'waiting') return 'Waiting';
  if (tone === 'blocked') return 'Blocked';
  return 'AI Thinking';
}

function HealthIndicator({ tone }: { tone: StatusTone }) {
  return <span className={styles.healthDot} data-tone={tone} aria-label={toneLabel(tone)} />;
}

function MetricCard({ label, value, detail, tone }: { label: string; value: string; detail: string; tone: StatusTone }) {
  return (
    <motion.article className={styles.metricCard} whileHover={{ y: -3 }} transition={{ duration: 0.18 }}>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <HealthIndicator tone={tone} />
      <p>{detail}</p>
    </motion.article>
  );
}

function SpecialistCard({ specialist }: { specialist: Specialist }) {
  return (
    <motion.article className={styles.specialistCard} whileHover={{ y: -3 }} transition={{ duration: 0.18 }}>
      <div className={styles.specialistTop}>
        <span className={styles.specialistAvatar}>{specialist.role.slice(0, 2).toUpperCase()}</span>
        <div>
          <strong>{specialist.role}</strong>
          <small>{specialist.update}</small>
        </div>
        <HealthIndicator tone={specialist.tone} />
      </div>
      <p>{specialist.task}</p>
      <div className={styles.progressTrack}>
        <span style={{ width: `${specialist.progress}%` }} />
      </div>
      <div className={styles.specialistMeta}>
        <span>{specialist.progress}% complete</span>
        <span>{specialist.confidence}% confidence</span>
      </div>
    </motion.article>
  );
}

export default function ArceusMissionWorkspace() {
  const [activeBottomTab, setActiveBottomTab] = useState('Tasks');
  const knowledgeNodes = useMemo(() => ['Authentication', 'JWT', 'Redis', 'Gateway', 'Database'], []);

  return (
    <main className={styles.aios}>
      <aside className={styles.sidebar} aria-label="Arceus Code navigation">
        <div className={styles.brand}>
          <span className={styles.logoMark}><Sparkles size={18} /></span>
          <div>
            <strong>Arceus Code</strong>
            <small>AI Organization OS</small>
          </div>
        </div>

        <nav className={styles.navList}>
          {sidebarItems.map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.label} type="button" className={styles.navItem} data-active={item.active || undefined}>
                <Icon size={17} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <section className={styles.workspace}>
        <header className={styles.topbar}>
          <button type="button" className={styles.workspaceSelector}>
            <FolderGit2 size={17} />
            Arceus Platform
          </button>
          <label className={styles.commandBar}>
            <Search size={17} />
            <input placeholder="Search missions, repositories, commands, specialists..." />
            <kbd>Ctrl K</kbd>
          </label>
          <div className={styles.topActions}>
            <button type="button" title="Organization health" className={styles.healthPill}>
              <span />
              Healthy
            </button>
            <button type="button" title="Notifications"><Bell size={18} /></button>
            <button type="button" title="Profile" className={styles.profileButton}>VR</button>
          </div>
        </header>

        <div className={styles.content}>
          <section className={styles.mainColumn}>
            <motion.section className={styles.missionHero} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
              <div>
                <span className={styles.eyebrow}><Zap size={15} /> Current Mission</span>
                <h1>Authentication Modernization</h1>
                <p>Arceus is coordinating an AI engineering organization to improve auth reliability, token recovery, security boundaries, and deployment evidence.</p>
              </div>
              <div className={styles.missionStats}>
                <span><b>Running</b>Status</span>
                <span><b>68%</b>Progress</span>
                <span><b>15 min</b>ETA</span>
                <span><b>High</b>Priority</span>
              </div>
            </motion.section>

            <section className={styles.gridTwo}>
              <article className={styles.panel}>
                <div className={styles.panelHeader}>
                  <div>
                    <span className={styles.eyebrow}>AI Organization</span>
                    <h2>Specialists executing this mission</h2>
                  </div>
                  <button type="button">View org</button>
                </div>
                <div className={styles.specialistGrid}>
                  {specialists.map((specialist) => (
                    <SpecialistCard key={specialist.role} specialist={specialist} />
                  ))}
                </div>
              </article>

              <aside className={styles.missionControl}>
                <div className={styles.panelHeader}>
                  <div>
                    <span className={styles.eyebrow}>Mission Control</span>
                    <h2>Execution state</h2>
                  </div>
                  <Command size={18} />
                </div>
                <div className={styles.controlRows}>
                  <div><span>Current phase</span><strong>Security review</strong></div>
                  <div><span>Next step</span><strong>Run auth regression tests</strong></div>
                  <div><span>Blocked tasks</span><strong>1 needs decision</strong></div>
                  <div><span>Approvals needed</span><strong>Security sign-off</strong></div>
                  <div><span>Risk level</span><strong>Medium</strong></div>
                </div>
                <article className={styles.recommendation}>
                  <BrainCircuit size={19} />
                  <div>
                    <strong>AI recommendation</strong>
                    <p>Require a human approval before production auth changes are deployed.</p>
                  </div>
                </article>
                <button type="button" className={styles.primaryButton}>Review Approval Queue</button>
              </aside>
            </section>

            <section className={styles.gridThree}>
              <MetricCard label="Open PRs" value="3" detail="2 ready for review" tone="running" />
              <MetricCard label="Architecture score" value="91" detail="Auth boundary improving" tone="complete" />
              <MetricCard label="Technical debt" value="Low" detail="1 medium-risk item" tone="waiting" />
              <MetricCard label="Test coverage" value="84%" detail="Regression suite queued" tone="running" />
              <MetricCard label="Build status" value="Passing" detail="Last check 4 min ago" tone="complete" />
              <MetricCard label="Deploy status" value="Staging" detail="Production held" tone="waiting" />
            </section>

            <section className={styles.bottomPanel}>
              <div className={styles.bottomTabs}>
                {bottomTabs.map((tab) => (
                  <button key={tab} type="button" data-active={tab === activeBottomTab || undefined} onClick={() => setActiveBottomTab(tab)}>
                    {tab === 'Terminal' ? <Terminal size={15} /> : tab === 'Tests' ? <TestTube2 size={15} /> : <Activity size={15} />}
                    {tab}
                  </button>
                ))}
              </div>
              <div className={styles.bottomBody}>
                <strong>{activeBottomTab}</strong>
                <p>Mission-scoped execution evidence appears here. The editor opens only when a task, file, or review requires it.</p>
              </div>
            </section>
          </section>

          <aside className={styles.rightColumn}>
            <article className={styles.panel}>
              <div className={styles.panelHeader}>
                <div>
                  <span className={styles.eyebrow}>Knowledge Graph</span>
                  <h2>Mission memory</h2>
                </div>
                <Network size={18} />
              </div>
              <div className={styles.knowledgeGraph}>
                {knowledgeNodes.map((node, index) => (
                  <div key={node} className={styles.knowledgeNode}>
                    <span>{node}</span>
                    {index < knowledgeNodes.length - 1 ? <i /> : null}
                  </div>
                ))}
              </div>
            </article>

            <article className={styles.panel}>
              <div className={styles.panelHeader}>
                <div>
                  <span className={styles.eyebrow}>Recent Decisions</span>
                  <h2>Human-governed choices</h2>
                </div>
                <ShieldCheck size={18} />
              </div>
              <div className={styles.decisionList}>
                <div><CheckCircle2 size={16} /><span>Keep production deploys behind human approval</span></div>
                <div><Database size={16} /><span>Store session recovery evidence in Redis-backed jobs</span></div>
                <div><GitPullRequest size={16} /><span>Require approved hunks only for PR creation</span></div>
              </div>
            </article>

            <article className={styles.panel}>
              <div className={styles.panelHeader}>
                <div>
                  <span className={styles.eyebrow}>Live Activity</span>
                  <h2>Organization timeline</h2>
                </div>
                <Clock3 size={18} />
              </div>
              <div className={styles.activityFeed}>
                {activity.map((item) => (
                  <div key={`${item.time}-${item.text}`} className={styles.activityRow}>
                    <time>{item.time}</time>
                    <HealthIndicator tone={item.tone} />
                    <div>
                      <strong>{item.actor}</strong>
                      <span>{item.text}</span>
                    </div>
                  </div>
                ))}
              </div>
            </article>

            <article className={styles.deployCard}>
              <FlaskConical size={20} />
              <div>
                <strong>Reviews waiting</strong>
                <p>Security found 1 production-risk item. Routine implementation can continue.</p>
              </div>
              <button type="button">Open Reviews</button>
            </article>
          </aside>
        </div>
      </section>
    </main>
  );
}
