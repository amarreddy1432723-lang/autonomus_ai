'use client';

import { useRouter } from 'next/navigation';
import {
  Bell,
  Brain,
  Check,
  ChevronRight,
  Cloud,
  Code2,
  FolderOpen,
  GitBranch,
  Globe2,
  Layers3,
  Settings,
  Sparkles,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiRequest } from '../../utils/api';
import { hasDesktopAuthToken, probeServiceHealth, serviceHealthCopy, type ServiceHealthSnapshot } from '../../utils/serviceHealth';
import { ACTIVE_PROJECT_KEY, OPEN_PROJECTS_KEY, type CodeProject } from '../workspace/workspacePageUtils';
import styles from './Launch.module.css';

type RecentProject = {
  id: string;
  name: string;
  status: string;
  lastOpened: string;
  tone: 'purple' | 'green' | 'blue';
  project?: CodeProject;
};

const SAMPLE_PROJECTS: RecentProject[] = [
  { id: 'sample-arceus', name: 'Arceus Platform', status: 'Active', lastOpened: '2 hours ago', tone: 'purple' },
  { id: 'sample-localadda', name: 'LocalAdda', status: 'Waiting Review', lastOpened: 'Yesterday', tone: 'green' },
  { id: 'sample-healthcare', name: 'Healthcare AI', status: 'Deploying', lastOpened: 'Now', tone: 'blue' },
];

function initialHealth(): ServiceHealthSnapshot {
  const copy = serviceHealthCopy('partially_online');
  return { state: 'partially_online', label: copy.label, detail: copy.detail, online: false, authReady: false, checkedAt: '' };
}

function projectTone(index: number): RecentProject['tone'] {
  return index % 3 === 0 ? 'purple' : index % 3 === 1 ? 'green' : 'blue';
}

function projectStatus(project: CodeProject, index: number): string {
  if ((project as any).status === 'archived') return 'Archived';
  if ((project as any).has_pending_patch) return 'Waiting Review';
  if ((project as any).deployment_status === 'deploying') return 'Deploying';
  return index === 0 ? 'Active' : 'Ready';
}

export default function LaunchPage() {
  const router = useRouter();
  const [health, setHealth] = useState<ServiceHealthSnapshot>(initialHealth);
  const [projects, setProjects] = useState<CodeProject[]>([]);
  const [openProjectIds, setOpenProjectIds] = useState<string[]>([]);
  const [activeProjectId, setActiveProjectId] = useState('');
  const [hydrated, setHydrated] = useState(false);

  const runChecks = useCallback(async () => {
    const openIds = JSON.parse(window.localStorage.getItem(OPEN_PROJECTS_KEY) || '[]');
    const activeId = window.localStorage.getItem(ACTIVE_PROJECT_KEY) || '';
    setOpenProjectIds(Array.isArray(openIds) ? openIds.slice(0, 3) : []);
    setActiveProjectId(activeId);

    const snapshot = await probeServiceHealth({ timeoutMs: 3500 });
    setHealth(snapshot);

    if (snapshot.online) {
      try {
        const data = await apiRequest('/api/v1/code/projects');
        setProjects(Array.isArray(data?.projects) ? data.projects : []);
      } catch {
        setProjects([]);
      }
    } else {
      setProjects([]);
    }
  }, []);

  useEffect(() => {
    setHydrated(true);
    void runChecks();
  }, [runChecks]);

  const authReady = hydrated && (health.authReady || hasDesktopAuthToken());
  const openProjects = useMemo(
    () => openProjectIds.map((id) => projects.find((project) => project.id === id)).filter(Boolean) as CodeProject[],
    [openProjectIds, projects],
  );
  const activeProject = projects.find((project) => project.id === activeProjectId) || openProjects[0] || null;
  const recentProjects = useMemo<RecentProject[]>(() => {
    const source = (openProjects.length ? openProjects : projects).slice(0, 3);
    if (!source.length) return SAMPLE_PROJECTS;
    return source.map((project, index) => ({
      id: project.id,
      name: project.name || `Project ${index + 1}`,
      status: projectStatus(project, index),
      lastOpened: index === 0 ? 'Recently' : 'This week',
      tone: projectTone(index),
      project,
    }));
  }, [openProjects, projects]);

  const openWorkspace = (project?: CodeProject) => {
    if (project?.id) router.push(`/workspace?project_id=${project.id}`);
    else router.push(activeProject ? `/workspace?project_id=${activeProject.id}` : '/workspace');
  };

  const actions = [
    {
      title: 'Build a New Product',
      subtitle: 'Start from an idea.',
      icon: <Sparkles size={28} />,
      accent: 'purple',
      onClick: () => router.push('/onboarding'),
    },
    {
      title: 'Open Existing Project',
      subtitle: 'Continue local development.',
      icon: <FolderOpen size={28} />,
      accent: 'blue',
      onClick: () => router.push('/workspace?action=open-folder'),
    },
    {
      title: 'Clone Repository',
      subtitle: 'GitHub, GitLab or Bitbucket.',
      icon: <Globe2 size={28} />,
      accent: 'purple',
      onClick: () => router.push('/workspace?drawer=git&action=clone'),
    },
    {
      title: 'Continue Previous Work',
      subtitle: 'Resume unfinished AI tasks.',
      icon: <Brain size={28} />,
      accent: 'blue',
      onClick: () => openWorkspace(),
    },
  ];

  const workforce = [
    { role: 'Engineering Manager', state: 'Thinking', tone: 'purple' },
    { role: 'Architect', state: 'Ready', tone: 'green' },
    { role: 'Frontend Team', state: 'Ready', tone: 'green' },
    { role: 'Backend Team', state: 'Ready', tone: 'green' },
    { role: 'QA', state: 'Ready', tone: 'green' },
  ];

  return (
    <main className={styles.launch}>
      <section className={styles.chrome} aria-label="Arceus Code opening screen">
        <header className={styles.topbar}>
          <button className={styles.brand} type="button" onClick={() => router.push('/launch')} aria-label="Arceus Code home">
            <span className={styles.logoMark}>
              <Layers3 size={26} />
            </span>
            <span>
              <strong>Arceus Code</strong>
              <small>AI Engineering Platform</small>
            </span>
          </button>

          <div className={styles.windowControls} aria-hidden="true">
            <span />
            <span />
            <span />
          </div>

          <nav className={styles.topActions} aria-label="Account and system">
            <button className={styles.iconButton} type="button" aria-label="Notifications">
              <Bell size={18} />
            </button>
            <button className={styles.iconButton} type="button" aria-label="Settings" onClick={() => router.push('/settings')}>
              <Settings size={18} />
            </button>
            <button className={styles.avatar} type="button" aria-label={authReady ? 'Profile' : 'Connect account'} onClick={() => router.push(authReady ? '/settings?tab=account' : '/auth/desktop')}>
              {authReady ? 'V' : <Code2 size={16} />}
            </button>
            <button className={styles.syncPill} type="button" onClick={() => void runChecks()} aria-label={`Cloud sync: ${health.label}`}>
              <Cloud size={16} />
              <span>{health.online ? 'Synced' : 'Local mode'}</span>
              <i data-state={health.online ? 'online' : 'warning'} />
            </button>
          </nav>
        </header>

        <section className={styles.hero}>
          <p className={styles.greeting}>Good Afternoon, Vamsi <span aria-hidden="true">👋</span></p>
          <h1>What are we building today?</h1>
        </section>

        <section className={styles.actionGrid} aria-label="Primary actions">
          {actions.map((action) => (
            <button key={action.title} className={styles.actionCard} data-accent={action.accent} type="button" onClick={action.onClick}>
              <span className={styles.actionIcon}>{action.icon}</span>
              <span className={styles.actionText}>
                <strong>{action.title}</strong>
                <small>{action.subtitle}</small>
              </span>
              <ChevronRight size={20} className={styles.chevron} />
            </button>
          ))}
        </section>

        <section className={styles.lowerGrid}>
          <article className={styles.recentCard}>
            <div className={styles.cardHeader}>
              <div>
                <h2>Recent Projects</h2>
                <p>Continue where your engineering team left off.</p>
              </div>
              <button type="button" className={styles.viewAll} onClick={() => router.push('/workspace')}>
                View All
                <ChevronRight size={15} />
              </button>
            </div>

            <div className={styles.projectRows}>
              {recentProjects.map((project) => (
                <div className={styles.projectRow} key={project.id}>
                  <span className={styles.projectIcon} data-tone={project.tone}>
                    {project.tone === 'green' ? 'LA' : project.tone === 'blue' ? <Check size={18} /> : <Layers3 size={18} />}
                  </span>
                  <strong>{project.name}</strong>
                  <span className={styles.badge} data-tone={project.tone}>{project.status}</span>
                  <span className={styles.lastOpened}>{project.lastOpened}</span>
                  <button type="button" onClick={() => openWorkspace(project.project)}>Open</button>
                </div>
              ))}
            </div>
          </article>

          <article className={styles.workforceCard}>
            <div className={styles.cardHeader}>
              <div>
                <h2>AI Workforce</h2>
                <p>Your engineering organization is ready.</p>
              </div>
            </div>
            <div className={styles.workforceRows}>
              {workforce.map((worker) => (
                <div key={worker.role} className={styles.workforceRow}>
                  <span className={styles.workerDot} data-tone={worker.tone} />
                  <strong>{worker.role}</strong>
                  <span data-tone={worker.tone}>{worker.state}</span>
                </div>
              ))}
            </div>
          </article>
        </section>

        <footer className={styles.footer}>
          <p>Everything is ready.</p>
          <button type="button" className={styles.startButton} onClick={() => router.push('/onboarding')}>
            <Sparkles size={22} />
            Start Building
          </button>
        </footer>
      </section>
    </main>
  );
}
