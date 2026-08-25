'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  Cloud,
  FileText,
  FolderOpen,
  GitBranch,
  Loader2,
  LogIn,
  SearchCheck,
  Settings,
  ShieldCheck,
} from 'lucide-react';
import { useMissionStore, type PersistedMission } from '../../stores/mission-store';
import { useRepositoryStore } from '../../stores/repository-store';
import { hasDesktopAuthToken } from '../../utils/serviceHealth';
import styles from './Onboarding.module.css';

type StepKey = 'welcome' | 'account' | 'repository' | 'analysis' | 'summary' | 'mission' | 'plans' | 'approval';
type RepoMode = 'local' | 'clone' | 'recent';

const STEPS: Array<{ key: StepKey; label: string }> = [
  { key: 'welcome', label: 'Welcome' },
  { key: 'account', label: 'Account' },
  { key: 'repository', label: 'Repository' },
  { key: 'analysis', label: 'Analysis' },
  { key: 'summary', label: 'Ready' },
  { key: 'mission', label: 'Mission' },
  { key: 'plans', label: 'Plans' },
  { key: 'approval', label: 'Approval' },
];

const EXAMPLES = [
  'Add Google Login',
  'Fix failing build',
  'Create missing tests',
  'Improve API error handling',
  'Add Stripe subscription billing',
];

const SCOPE_OPTIONS = ['Entire Project', 'Specific Module', 'Current Folder', 'Selected Files'];

function getElectron() {
  if (typeof window === 'undefined') return null;
  return {
    desktop: (window as any).arceusDesktop,
    legacy: (window as any).electron,
  };
}

function stepIndex(step: StepKey) {
  return Math.max(0, STEPS.findIndex((item) => item.key === step));
}

function projectName(rootPath?: string) {
  return String(rootPath || '').split(/[\\/]/).filter(Boolean).pop() || 'Repository';
}

function errorRecovery(error?: string) {
  const text = error || 'Repository analysis did not complete.';
  const lower = text.toLowerCase();
  if (lower.includes('package.json')) {
    return {
      reason: 'package.json not found',
      suggestions: ['Choose the application root folder', 'Open a repository that has build metadata', 'Continue local-only and add setup notes later'],
    };
  }
  if (lower.includes('unauthorized') || lower.includes('token') || lower.includes('clerk')) {
    return {
      reason: 'Account token is missing or expired',
      suggestions: ['Sign in again', 'Continue locally without cloud missions', 'Retry after backend auth is ready'],
    };
  }
  return {
    reason: text,
    suggestions: ['Retry analysis', 'Choose another folder', 'Open documentation'],
  };
}

function analysisRows(status: string) {
  const done = status === 'ready';
  const failed = status === 'failed';
  return [
    ['Loading repository', done || failed ? 'done' : status === 'analyzing' ? 'running' : 'waiting'],
    ['Analyzing structure', done ? 'done' : status === 'analyzing' ? 'running' : failed ? 'failed' : 'waiting'],
    ['Discovering languages', done ? 'done' : 'waiting'],
    ['Building dependency graph', done ? 'done' : 'waiting'],
    ['Understanding architecture', done ? 'done' : 'waiting'],
  ] as const;
}

function planCards(mission: PersistedMission | null) {
  const tasks = mission?.task_count || 8;
  const risk = mission?.compiled_plan?.understanding?.risk_level || 'medium';
  return [
    {
      name: 'Plan A',
      title: 'Minimal changes',
      effort: '2 hours',
      risk: 'Low risk',
      complexity: 'Low',
      affected: 'Smallest safe surface',
      summary: 'Limit the work to the minimum patch needed to satisfy the goal.',
    },
    {
      name: 'Plan B',
      title: 'Balanced implementation',
      effort: '4 hours',
      risk: `${risk} risk`,
      complexity: 'Medium',
      affected: `${tasks} planned tasks`,
      summary: 'Recommended path with implementation, tests, and evidence without over-expanding scope.',
      recommended: true,
    },
    {
      name: 'Plan C',
      title: 'Architecture-first',
      effort: '8 hours',
      risk: 'Higher flexibility',
      complexity: 'High',
      affected: 'Broader modules and docs',
      summary: 'Improve boundaries and supporting docs before the direct implementation work.',
    },
  ];
}

export default function OnboardingPage() {
  const router = useRouter();
  const repository = useRepositoryStore();
  const missionRuntime = useMissionStore();
  const [step, setStep] = useState<StepKey>('welcome');
  const [repoMode, setRepoMode] = useState<RepoMode>('local');
  const [manualPath, setManualPath] = useState('');
  const [cloneUrl, setCloneUrl] = useState('');
  const [missionGoal, setMissionGoal] = useState('');
  const [scope, setScope] = useState(SCOPE_OPTIONS[0]);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    setSignedIn(hasDesktopAuthToken());
    try {
      const mode = new URLSearchParams(window.location.search).get('mode');
      if (mode === 'clone') setRepoMode('clone');
      if (mode === 'open') setRepoMode('local');
    } catch {
      // Keep defaults.
    }
  }, []);

  const currentStep = stepIndex(step);
  const progress = Math.round(((currentStep + 1) / STEPS.length) * 100);
  const repoReady = repository.status === 'ready';
  const missionReady = Boolean(missionRuntime.mission);
  const recovery = errorRecovery(repository.error || missionRuntime.error);
  const detectedSignals = useMemo(() => [
    ['Repository', projectName(repository.rootPath || repository.name)],
    ['Languages', repository.languages.join(', ') || 'Not detected'],
    ['Frameworks', repository.frameworks.join(', ') || 'Not detected'],
    ['Modules', String(repository.services.length || repository.entryPoints.length || 0)],
    ['Tests', repository.testCommands.length ? repository.testCommands.join(', ') : 'Not detected'],
    ['Files', repository.scannedFiles ? String(repository.scannedFiles) : 'Pending'],
  ], [repository]);

  const goBack = () => {
    const previous = STEPS[Math.max(currentStep - 1, 0)]?.key;
    if (previous) setStep(previous);
  };

  const chooseLocalFolder = async () => {
    setBusy('folder');
    setNotice('');
    try {
      const electron = getElectron();
      let selectedPath = '';
      if (electron?.desktop?.workspace?.openDirectory) {
        const result = await electron.desktop.workspace.openDirectory({ trusted: true });
        const payload = result?.ok ? result.result : result;
        selectedPath = payload?.rootPath || '';
      } else if (electron?.legacy?.workspace?.openDirectory) {
        const result = await electron.legacy.workspace.openDirectory({ trusted: true });
        selectedPath = result?.data?.rootPath || result?.rootPath || '';
      } else if (electron?.legacy?.selectDirectory) {
        selectedPath = await electron.legacy.selectDirectory();
      }
      if (!selectedPath) {
        setNotice('Choose a folder, or paste a local repository path.');
        return;
      }
      setManualPath(selectedPath);
      await analyzePath(selectedPath);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not open the selected folder.');
    } finally {
      setBusy('');
    }
  };

  const analyzePath = async (pathValue = manualPath) => {
    const rootPath = pathValue.trim();
    if (!rootPath) {
      setNotice('Paste or choose a repository folder first.');
      return;
    }
    setStep('analysis');
    setBusy('analysis');
    setNotice('');
    await repository.analyzeRepository(rootPath);
    setBusy('');
    setStep(repository.status === 'failed' ? 'analysis' : 'summary');
  };

  const createMission = async () => {
    const goal = missionGoal.trim();
    if (!goal) {
      setNotice('Describe your mission before creating plans.');
      return;
    }
    setBusy('mission');
    setNotice('');
    const mission = await missionRuntime.createMission(`${goal}\n\nRepository Scope: ${scope}`, repository);
    setBusy('');
    if (mission) setStep('plans');
    else setNotice(missionRuntime.error || 'Could not create mission plans.');
  };

  const approveMission = async () => {
    setBusy('approval');
    const mission = await missionRuntime.approveMission();
    setBusy('');
    if (mission) {
      try {
        window.localStorage.setItem('arceus.onboarding.completed', 'true');
      } catch {
        // Ignore storage failures.
      }
      router.push(`/workspace?mission_id=${encodeURIComponent(mission.mission_id)}&root_path=${encodeURIComponent(repository.rootPath || '')}`);
    }
  };

  return (
    <main className={styles.onboarding}>
      <section className={styles.window} aria-label="Arceus first mission onboarding">
        <header className={styles.header}>
          <button type="button" className={styles.brand} onClick={() => router.push('/launch')}>
            <span>A</span>
            <div>
              <strong>Arceus Code</strong>
              <small>First mission setup</small>
            </div>
          </button>
          <div className={styles.accountState}>
            {signedIn ? (
              <>
                <Cloud size={15} />
                <span>Vamsi Krishna · Pro Plan · Connected</span>
              </>
            ) : (
              <>
                <LogIn size={15} />
                <span>Not Signed In</span>
                <button type="button" onClick={() => router.push('/auth/desktop')}>Sign In</button>
              </>
            )}
          </div>
        </header>

        <div className={styles.progressBar} aria-label={`Setup progress ${progress}%`}>
          <i><em style={{ width: `${progress}%` }} /></i>
          <span>{progress}%</span>
        </div>

        <nav className={styles.steps} aria-label="Onboarding stages">
          {STEPS.map((item, index) => (
            <button
              type="button"
              key={item.key}
              data-state={index < currentStep ? 'done' : index === currentStep ? 'active' : 'pending'}
              onClick={() => index <= currentStep && setStep(item.key)}
              disabled={index > currentStep}
            >
              {index < currentStep ? <CheckCircle2 size={14} /> : index + 1}
              {item.label}
            </button>
          ))}
        </nav>

        {notice && <div className={styles.notice}>{notice}</div>}

        <section className={styles.body}>
          {step === 'welcome' && (
            <div className={styles.centerStep}>
              <h1>Welcome to Arceus</h1>
              <p>Build software with an AI engineering team. Start by opening a repository and creating one clear mission.</p>
              <div className={styles.heroActions}>
                <button type="button" className={styles.primary} onClick={() => setStep('repository')}>
                  <FolderOpen size={18} /> Open Folder
                </button>
                <button type="button" className={styles.secondary} onClick={() => { setRepoMode('clone'); setStep('repository'); }}>
                  <GitBranch size={18} /> Clone Repository
                </button>
              </div>
            </div>
          )}

          {step === 'account' && (
            <div className={styles.centerStep}>
              <h1>{signedIn ? 'Account connected.' : 'Sign in or continue locally.'}</h1>
              <p>Sign in unlocks cloud sync, GitHub PRs, billing, and shared mission history. Local folder, editor, and terminal can still work without cloud actions.</p>
              <div className={styles.heroActions}>
                {!signedIn && <button type="button" className={styles.primary} onClick={() => router.push('/auth/desktop')}>Sign In</button>}
                <button type="button" className={styles.secondary} onClick={() => setStep('repository')}>Continue Local</button>
              </div>
            </div>
          )}

          {step === 'repository' && (
            <div className={styles.repositoryStep}>
              <div className={styles.sectionTitle}>
                <p>Repository Selection</p>
                <h1>Choose the codebase Arceus should understand.</h1>
              </div>
              <div className={styles.repoModes}>
                {[
                  ['local', 'Open Folder', 'Use a trusted local repository.', FolderOpen],
                  ['clone', 'Clone Git Repository', 'GitHub, GitLab, or Bitbucket.', GitBranch],
                  ['recent', 'Recent Projects', 'Continue a known workspace.', FileText],
                ].map(([id, title, detail, Icon]) => (
                  <button type="button" key={String(id)} data-active={repoMode === id} onClick={() => setRepoMode(id as RepoMode)}>
                    <Icon size={22} />
                    <strong>{String(title)}</strong>
                    <small>{String(detail)}</small>
                  </button>
                ))}
              </div>

              {repoMode === 'local' && (
                <div className={styles.repoForm}>
                  <button type="button" className={styles.primary} onClick={chooseLocalFolder} disabled={!!busy}>
                    <FolderOpen size={18} /> {busy === 'folder' ? 'Opening...' : 'Open Folder'}
                  </button>
                  <input value={manualPath} onChange={(event) => setManualPath(event.target.value)} placeholder="Paste a local repository path" />
                  <button type="button" className={styles.secondary} onClick={() => void analyzePath()} disabled={!!busy || !manualPath.trim()}>
                    Analyze Repository
                  </button>
                </div>
              )}

              {repoMode === 'clone' && (
                <div className={styles.repoForm}>
                  <input value={cloneUrl} onChange={(event) => setCloneUrl(event.target.value)} placeholder="https://github.com/company/project.git" />
                  <button type="button" className={styles.primary} onClick={() => router.push(`/workspace?drawer=git&action=clone&repo=${encodeURIComponent(cloneUrl.trim())}`)} disabled={!cloneUrl.trim()}>
                    Continue to Clone <ArrowRight size={18} />
                  </button>
                </div>
              )}

              {repoMode === 'recent' && (
                <div className={styles.repoForm}>
                  <p>Recent projects are shown on the welcome screen after you open a trusted folder.</p>
                  <button type="button" className={styles.primary} onClick={() => router.push('/workspace')}>Open Workspace</button>
                </div>
              )}
            </div>
          )}

          {step === 'analysis' && (
            <div className={styles.analysisStep}>
              <div className={styles.sectionTitle}>
                <p>Repository Analysis</p>
                <h1>{repository.status === 'failed' ? 'Could not analyze repository.' : 'Understanding your repository.'}</h1>
              </div>
              <div className={styles.analysisList}>
                {analysisRows(repository.status).map(([label, state]) => (
                  <article key={label} data-state={state}>
                    {state === 'done' ? <CheckCircle2 size={18} /> : state === 'failed' ? <AlertCircle size={18} /> : state === 'running' ? <Loader2 size={18} className={styles.spin} /> : <SearchCheck size={18} />}
                    <span>{label}</span>
                    <small>{state}</small>
                  </article>
                ))}
              </div>
              {repository.status === 'failed' && (
                <div className={styles.errorBox}>
                  <strong>Reason</strong>
                  <p>{recovery.reason}</p>
                  <strong>Suggestions</strong>
                  <div>
                    {recovery.suggestions.map((suggestion) => <span key={suggestion}>{suggestion}</span>)}
                  </div>
                  <div className={styles.heroActions}>
                    <button type="button" className={styles.primary} onClick={() => void analyzePath()} disabled={!manualPath.trim()}>Retry</button>
                    <button type="button" className={styles.secondary} onClick={() => setStep('repository')}>Choose another folder</button>
                    <button type="button" className={styles.secondary} onClick={() => router.push('/docs')}>Open Documentation</button>
                  </div>
                </div>
              )}
            </div>
          )}

          {step === 'summary' && (
            <div className={styles.reportStep}>
              <div className={styles.sectionTitle}>
                <p>Mission Ready</p>
                <h1>{projectName(repository.rootPath || repository.name)} is ready.</h1>
              </div>
              <div className={styles.signalGrid}>
                {detectedSignals.map(([label, value]) => (
                  <div key={label}>
                    <small>{label}</small>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
              <div className={styles.readyBox}>
                <ShieldCheck size={20} />
                <div>
                  <strong>Ready</strong>
                  <p>Arceus can now create a mission plan with scope, tasks, risk, and approval before execution.</p>
                </div>
              </div>
            </div>
          )}

          {step === 'mission' && (
            <div className={styles.missionStep}>
              <div className={styles.sectionTitle}>
                <p>Mission Composer</p>
                <h1>Describe your goal.</h1>
              </div>
              <textarea value={missionGoal} onChange={(event) => setMissionGoal(event.target.value)} placeholder="Add Google Authentication" />
              <div className={styles.scopeRow}>
                {SCOPE_OPTIONS.map((option) => (
                  <button type="button" key={option} data-active={scope === option} onClick={() => setScope(option)}>{option}</button>
                ))}
              </div>
              <div className={styles.examples}>
                {EXAMPLES.map((example) => (
                  <button type="button" key={example} onClick={() => setMissionGoal(example)}>{example}</button>
                ))}
              </div>
            </div>
          )}

          {step === 'plans' && (
            <div className={styles.plansStep}>
              <div className={styles.sectionTitle}>
                <p>Three Engineering Plans</p>
                <h1>Choose the implementation strategy.</h1>
              </div>
              <div className={styles.planPreview}>
                {planCards(missionRuntime.mission).map((plan) => (
                  <article key={plan.name} data-recommended={plan.recommended || undefined}>
                    <span>{plan.name}</span>
                    <strong>{plan.title}</strong>
                    <p>{plan.summary}</p>
                    <div>
                      <small>{plan.effort}</small>
                      <small>{plan.risk}</small>
                      <small>{plan.complexity}</small>
                      <small>{plan.affected}</small>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          )}

          {step === 'approval' && (
            <div className={styles.approvalStep}>
              <div className={styles.sectionTitle}>
                <p>Mission Approval</p>
                <h1>{missionRuntime.mission?.goal.split('\n')[0] || missionGoal || 'Mission'}</h1>
              </div>
              <div className={styles.approvalCard}>
                <div><small>Areas</small><strong>Backend · Frontend · Tests · Documentation</strong></div>
                <div><small>Estimated Files</small><strong>{Math.max(4, missionRuntime.mission?.task_count || 8)}</strong></div>
                <div><small>Estimated Tasks</small><strong>{missionRuntime.mission?.task_count || 8}</strong></div>
                <div><small>Estimated Risk</small><strong>{missionRuntime.mission?.compiled_plan?.understanding?.risk_level || 'Medium'}</strong></div>
                <div><small>Approval</small><strong>{missionReady ? 'Required before execution' : 'Create mission first'}</strong></div>
              </div>
              {missionRuntime.error && <div className={styles.notice}>{missionRuntime.error}</div>}
            </div>
          )}
        </section>

        <footer className={styles.footer}>
          <button type="button" className={styles.secondary} onClick={goBack} disabled={currentStep === 0}>
            <ChevronLeft size={18} /> Back
          </button>

          {step === 'welcome' && <button type="button" className={styles.primary} onClick={() => setStep('account')}>Continue <ArrowRight size={18} /></button>}
          {step === 'account' && <button type="button" className={styles.primary} onClick={() => setStep('repository')}>Continue <ArrowRight size={18} /></button>}
          {step === 'repository' && repoMode !== 'clone' && <button type="button" className={styles.primary} onClick={() => manualPath.trim() ? void analyzePath() : setNotice('Choose or paste a repository first.')} disabled={repoMode === 'local' && !manualPath.trim()}>Analyze Repository <ArrowRight size={18} /></button>}
          {step === 'analysis' && repoReady && <button type="button" className={styles.primary} onClick={() => setStep('summary')}>View Summary <ArrowRight size={18} /></button>}
          {step === 'summary' && <button type="button" className={styles.primary} onClick={() => setStep('mission')}>Create Mission <ArrowRight size={18} /></button>}
          {step === 'mission' && <button type="button" className={styles.primary} onClick={createMission} disabled={!missionGoal.trim() || !repoReady || busy === 'mission'}>{busy === 'mission' ? 'Compiling Mission' : 'Create Plans'} <ArrowRight size={18} /></button>}
          {step === 'plans' && <button type="button" className={styles.primary} onClick={() => setStep('approval')}>Select Recommended Plan <ArrowRight size={18} /></button>}
          {step === 'approval' && <button type="button" className={styles.primary} onClick={approveMission} disabled={!missionReady || busy === 'approval'}>{busy === 'approval' ? 'Approving' : 'Approve Mission'} <ArrowRight size={18} /></button>}
        </footer>
      </section>
    </main>
  );
}
