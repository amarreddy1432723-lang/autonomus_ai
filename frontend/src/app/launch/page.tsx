'use client';

import { useRouter } from 'next/navigation';
import {
  Bell,
  ChevronRight,
  Cloud,
  FolderOpen,
  GitBranch,
  History,
  LogIn,
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
  const [showSplash, setShowSplash] = useState(true);
  const [health, setHealth] = useState<ServiceHealthSnapshot>(initialHealth);
  const [projects, setProjects] = useState<CodeProject[]>([]);
  const [openProjectIds, setOpenProjectIds] = useState<string[]>([]);
  const [activeProjectId, setActiveProjectId] = useState('');
  const [hydrated, setHydrated] = useState(false);

  const runChecks = useCallback(async () => {
    const openIds = JSON.parse(window.localStorage.getItem(OPEN_PROJECTS_KEY) || '[]');
    const activeId = window.localStorage.getItem(ACTIVE_PROJECT_KEY) || '';
    setOpenProjectIds(Array.isArray(openIds) ? openIds.slice(0, 6) : []);
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
    const timer = window.setTimeout(() => setShowSplash(false), 1200);
    setHydrated(true);
    void runChecks();
    return () => window.clearTimeout(timer);
  }, [runChecks]);

  const authReady = hydrated && (health.authReady || hasDesktopAuthToken());
  const openProjects = useMemo(
    () => openProjectIds.map((id) => projects.find((project) => project.id === id)).filter(Boolean) as CodeProject[],
    [openProjectIds, projects],
  );
  const activeProject = projects.find((project) => project.id === activeProjectId) || openProjects[0] || null;
  const recentProjects = useMemo<RecentProject[]>(() => {
    const source = (openProjects.length ? openProjects : projects).slice(0, 5);
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

  if (showSplash) {
    return (
      <main className={styles.splash} aria-label="Arceus is initializing">
        <span className={styles.splashMark}>A</span>
        <h1>Arceus</h1>
        <p>AI Engineering Platform</p>
        <i><em /></i>
        <span>Initializing...</span>
      </main>
    );
  }

  return (
    <main className={styles.launch}>
      <section className={styles.chrome} aria-label="Arceus Code welcome screen">
        <header className={styles.topbar}>
          <button className={styles.brand} type="button" onClick={() => router.push('/launch')} aria-label="Arceus Code home">
            <span className={styles.logoMark}>A</span>
            <span>
              <strong>Arceus Code</strong>
              <small>AI Engineering Platform</small>
            </span>
          </button>

          <nav className={styles.topActions} aria-label="Account and system">
            <button className={styles.accountButton} type="button" onClick={() => router.push(authReady ? '/settings?tab=account' : '/auth/desktop')}>
              {authReady ? (
                <>
                  <span className={styles.avatar}>VK</span>
                  <span><strong>Vamsi Krishna</strong><small>Pro Plan</small></span>
                </>
              ) : (
                <>
                  <LogIn size={16} />
                  <span><strong>Not Signed In</strong><small>Continue locally available</small></span>
                </>
              )}
            </button>
            {!authReady && (
              <button className={styles.signInButton} type="button" onClick={() => router.push('/auth/desktop')}>
                Connect Account
              </button>
            )}
            <button className={styles.iconButton} type="button" aria-label="Notifications">
              <Bell size={18} />
            </button>
            <button className={styles.iconButton} type="button" aria-label="Settings" onClick={() => router.push('/settings')}>
              <Settings size={18} />
            </button>
            <button className={styles.syncPill} type="button" onClick={() => void runChecks()} aria-label={`Cloud sync: ${health.label}`}>
              <Cloud size={16} />
              <span>{health.online ? 'Connected' : 'Local mode'}</span>
              <i data-state={health.online ? 'online' : 'warning'} />
            </button>
          </nav>
        </header>

        <section className={styles.hero}>
          <p className={styles.greeting}>Welcome to Arceus</p>
          <h1>{recentProjects.length ? 'Continue building with your AI engineering team.' : "Let's start by opening a project."}</h1>
          <p className={styles.heroSubcopy}>Build software with an AI engineering team. Open a repository, let Arceus understand it, then create your first mission.</p>
        </section>

        <section className={styles.primaryWelcomeActions} aria-label="Start options">
          <button type="button" className={styles.startCard} onClick={() => router.push('/onboarding?mode=open')}>
            <FolderOpen size={24} />
            <strong>Open Folder</strong>
            <span>Use an existing local repository.</span>
            <ChevronRight size={18} />
          </button>
          <button type="button" className={styles.startCard} onClick={() => router.push('/onboarding?mode=clone')}>
            <GitBranch size={24} />
            <strong>Clone Repository</strong>
            <span>GitHub, GitLab, or Bitbucket.</span>
            <ChevronRight size={18} />
          </button>
          {recentProjects.length > 0 && (
            <button type="button" className={styles.startCard} onClick={() => openWorkspace()}>
              <History size={24} />
              <strong>Continue Last Mission</strong>
              <span>Resume the most recent workspace.</span>
              <ChevronRight size={18} />
            </button>
          )}
        </section>

        {recentProjects.length > 0 && (
          <section className={styles.recentCard}>
            <div className={styles.cardHeader}>
              <div>
                <h2>Recent Projects</h2>
                <p>Pinned and recently opened workspaces.</p>
              </div>
              <button type="button" className={styles.viewAll} onClick={() => router.push('/workspace')}>
                Open Another Folder
                <ChevronRight size={15} />
              </button>
            </div>
            <div className={styles.projectRows}>
              {recentProjects.map((project) => (
                <div className={styles.projectRow} key={project.id}>
                  <span className={styles.projectIcon} data-tone={project.tone}>{project.name.slice(0, 2).toUpperCase()}</span>
                  <strong>{project.name}</strong>
                  <span className={styles.badge} data-tone={project.tone}>{project.status}</span>
                  <span className={styles.lastOpened}>{project.lastOpened}</span>
                  <button type="button" onClick={() => openWorkspace(project.project)}>Open</button>
                </div>
              ))}
            </div>
          </section>
        )}

        {recentProjects.length === 0 && (
          <section className={styles.firstRunHint}>
            <Sparkles size={18} />
            <p>No projects yet. Arceus will show repository analysis, mission plans, and activity after you open a folder.</p>
          </section>
        )}

        <footer className={styles.footer}>
          <button type="button" className={styles.textButton} onClick={() => router.push('/settings')}>
            Settings
          </button>
          <span>Ctrl+O Open Folder · Ctrl+Shift+M Create Mission · Ctrl+K Command Palette</span>
        </footer>
      </section>
    </main>
  );
}
