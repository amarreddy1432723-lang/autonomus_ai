'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowRight,
  Check,
  ChevronLeft,
  Cloud,
  FileText,
  FolderOpen,
  GitBranch,
  Lock,
  Play,
  Radar,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useRepositoryStore } from '../../stores/repository-store';
import { hasDesktopAuthToken } from '../../utils/serviceHealth';
import styles from './Onboarding.module.css';

type StepKey = 'welcome' | 'terms' | 'account' | 'repository' | 'report' | 'mission';
type RepoMode = 'local' | 'clone' | 'recent';

const STEPS: Array<{ key: StepKey; label: string }> = [
  { key: 'welcome', label: 'Welcome' },
  { key: 'terms', label: 'Terms' },
  { key: 'account', label: 'Account' },
  { key: 'repository', label: 'Repository' },
  { key: 'report', label: 'Report' },
  { key: 'mission', label: 'Mission' },
];

const EXAMPLES = [
  'Implement Google Login',
  'Fix build failures',
  'Write missing tests',
  'Improve accessibility',
  'Refactor backend service boundaries',
  'Add Stripe subscription billing',
];

const CAPABILITIES: Array<[string, LucideIcon]> = [
  ['AI Repository Analysis', Radar],
  ['Mission Planning', FileText],
  ['Multi-Agent Execution', Sparkles],
  ['Safe Patch Review', ShieldCheck],
];

const REPO_MODES: Array<[RepoMode, string, string, LucideIcon]> = [
  ['local', 'Open Local Folder', 'Use a trusted folder on this computer.', FolderOpen],
  ['clone', 'Clone Git Repository', 'Paste a GitHub, GitLab, or Bitbucket URL.', GitBranch],
  ['recent', 'Recent Projects', 'Continue a project already known to Arceus.', Play],
];

function stepIndex(step: StepKey) {
  return Math.max(0, STEPS.findIndex((item) => item.key === step));
}

function getElectron() {
  if (typeof window === 'undefined') return null;
  return (window as any).electron;
}

function pathName(value: string) {
  return value.split(/[\\/]/).filter(Boolean).pop() || 'Repository';
}

export default function OnboardingPage() {
  const router = useRouter();
  const repository = useRepositoryStore();
  const [step, setStep] = useState<StepKey>('welcome');
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [telemetry, setTelemetry] = useState(true);
  const [repoMode, setRepoMode] = useState<RepoMode>('local');
  const [manualPath, setManualPath] = useState('');
  const [cloneUrl, setCloneUrl] = useState('');
  const [mission, setMission] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState('');

  const currentStep = stepIndex(step);
  const signedIn = hasDesktopAuthToken();
  const canContinueFromTerms = acceptedTerms;
  const canContinueFromRepo = repository.status === 'ready' || manualPath.trim().length > 0 || cloneUrl.trim().length > 0;
  const missionText = mission.trim();
  const progress = Math.round(((currentStep + 1) / STEPS.length) * 100);

  const detectedSignals = useMemo(() => {
    const rows = [
      ['Languages', repository.languages.join(', ') || 'Not detected yet'],
      ['Frameworks', repository.frameworks.join(', ') || 'Not detected yet'],
      ['Package Manager', repository.packageManagers.join(', ') || 'Not detected yet'],
      ['Tests', repository.testCommands.join(', ') || 'Not detected yet'],
      ['Architecture', repository.architectureStyle || 'Not detected yet'],
      ['Project Size', repository.scannedFiles ? `${repository.scannedFiles} files scanned` : 'Pending scan'],
    ];
    return rows;
  }, [repository]);

  const goNext = () => {
    const next = STEPS[Math.min(currentStep + 1, STEPS.length - 1)]?.key;
    if (next) setStep(next);
  };

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
      if (electron?.workspace?.openDirectory) {
        const result = await electron.workspace.openDirectory({ trusted: true });
        selectedPath = result?.data?.rootPath || result?.rootPath || result?.path || '';
      } else if (electron?.selectDirectory) {
        selectedPath = await electron.selectDirectory();
      }

      if (!selectedPath) {
        setNotice('Choose a folder, or paste a local path to continue in browser mode.');
        return;
      }
      setManualPath(selectedPath);
      await repository.analyzeRepository(selectedPath);
      setStep('report');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not open the selected folder.');
    } finally {
      setBusy('');
    }
  };

  const analyzeManualPath = async () => {
    const rootPath = manualPath.trim();
    if (!rootPath) {
      setNotice('Paste a local repository path first.');
      return;
    }
    setBusy('analyze');
    setNotice('');
    try {
      await repository.analyzeRepository(rootPath);
      setStep('report');
    } finally {
      setBusy('');
    }
  };

  const startMission = () => {
    const params = new URLSearchParams();
    if (repository.repositoryId) params.set('repository_id', repository.repositoryId);
    if (repository.rootPath) params.set('root_path', repository.rootPath);
    if (missionText) params.set('idea', missionText);
    params.set('stage', 'mission');
    try {
      window.localStorage.setItem('arceus.onboarding.completed', 'true');
      window.localStorage.setItem('arceus.telemetry.preference', telemetry ? 'enabled' : 'disabled');
    } catch {
      // Ignore storage failures.
    }
    router.push(`/workspace?${params.toString()}`);
  };

  return (
    <main className={styles.onboarding}>
      <section className={styles.window} aria-label="Arceus first-run onboarding">
        <header className={styles.header}>
          <button type="button" className={styles.brand} onClick={() => router.push('/launch')} aria-label="Back to Arceus Code">
            <span><Sparkles size={22} /></span>
            <div>
              <strong>Arceus Code</strong>
              <small>First-run setup</small>
            </div>
          </button>
          <div className={styles.progress} aria-label={`Onboarding progress ${progress}%`}>
            <i><em style={{ width: `${progress}%` }} /></i>
            <span>{progress}%</span>
          </div>
        </header>

        <nav className={styles.steps} aria-label="Setup stages">
          {STEPS.map((item, index) => (
            <button
              type="button"
              key={item.key}
              data-state={index < currentStep ? 'done' : index === currentStep ? 'active' : 'pending'}
              onClick={() => index <= currentStep && setStep(item.key)}
              disabled={index > currentStep}
            >
              <span>{index < currentStep ? <Check size={13} /> : index + 1}</span>
              {item.label}
            </button>
          ))}
        </nav>

        {notice && <div className={styles.notice}>{notice}</div>}

        <section className={styles.body}>
          {step === 'welcome' && (
            <div className={styles.heroStep}>
              <p>Autonomous Software Engineering Platform</p>
              <h1>Welcome to Arceus.</h1>
              <strong>Connect a repository, understand it, choose a plan, and watch your AI engineering team execute with evidence.</strong>
              <div className={styles.capabilities}>
                {CAPABILITIES.map(([label, Icon]) => <span key={label}><Icon size={16} /> {label}</span>)}
              </div>
              <button type="button" className={styles.primary} onClick={goNext}>
                Start <ArrowRight size={18} />
              </button>
            </div>
          )}

          {step === 'terms' && (
            <div className={styles.twoColumn}>
              <article className={styles.card}>
                <Lock size={24} />
                <h2>Workspace trust</h2>
                <p>Arceus reads the repository you select. File writes, terminal commands, dependency installs, commits, and PRs remain governed by review and policy gates.</p>
                <label className={styles.checkRow}>
                  <input type="checkbox" checked={acceptedTerms} onChange={(event) => setAcceptedTerms(event.target.checked)} />
                  <span>I understand Arceus will operate only inside trusted workspaces and governed actions.</span>
                </label>
              </article>
              <article className={styles.card}>
                <Cloud size={24} />
                <h2>Telemetry preference</h2>
                <p>Help improve reliability by sharing product diagnostics. Source code, prompts, secrets, and repository content are not sent as telemetry.</p>
                <label className={styles.toggleRow}>
                  <span>{telemetry ? 'Diagnostics enabled' : 'Diagnostics disabled'}</span>
                  <input type="checkbox" checked={telemetry} onChange={(event) => setTelemetry(event.target.checked)} />
                </label>
              </article>
            </div>
          )}

          {step === 'account' && (
            <div className={styles.centerStep}>
              <h1>{signedIn ? 'Account connected.' : 'Connect your account.'}</h1>
              <p>{signedIn ? 'Your desktop session has an account token. You can continue to repository setup.' : 'Sign in unlocks cloud missions, GitHub PR flow, billing, and synced mission history. Local folder mode still works without cloud actions.'}</p>
              <div className={styles.buttonRow}>
                {!signedIn && <button type="button" className={styles.secondary} onClick={() => router.push('/auth/desktop')}>Connect account</button>}
                <button type="button" className={styles.primary} onClick={goNext}>Continue <ArrowRight size={18} /></button>
              </div>
            </div>
          )}

          {step === 'repository' && (
            <div className={styles.repositoryStep}>
              <div className={styles.sectionTitle}>
                <p>Repository Connection</p>
                <h1>Choose the codebase Arceus should understand.</h1>
              </div>
              <div className={styles.repoModes}>
                {REPO_MODES.map(([id, title, detail, Icon]) => {
                  return (
                    <button type="button" key={id} data-active={repoMode === id} onClick={() => setRepoMode(id)}>
                      <Icon size={22} />
                      <strong>{title}</strong>
                      <small>{detail}</small>
                    </button>
                  );
                })}
              </div>

              {repoMode === 'local' && (
                <div className={styles.repoForm}>
                  <button type="button" className={styles.primary} onClick={chooseLocalFolder} disabled={!!busy}>
                    <FolderOpen size={18} /> {busy === 'folder' ? 'Opening...' : 'Choose Folder'}
                  </button>
                  <div className={styles.orLine}>or paste a path</div>
                  <input value={manualPath} onChange={(event) => setManualPath(event.target.value)} placeholder="C:\Users\you\Projects\my-app" />
                  <button type="button" className={styles.secondary} onClick={analyzeManualPath} disabled={!!busy || !manualPath.trim()}>
                    {busy === 'analyze' ? 'Scanning Repository...' : 'Analyze Repository'}
                  </button>
                </div>
              )}

              {repoMode === 'clone' && (
                <div className={styles.repoForm}>
                  <input value={cloneUrl} onChange={(event) => setCloneUrl(event.target.value)} placeholder="https://github.com/company/project.git" />
                  <p>Clone execution will open the workspace Git drawer. Arceus will never push without confirmation.</p>
                  <button type="button" className={styles.primary} onClick={() => router.push(`/workspace?drawer=git&action=clone&repo=${encodeURIComponent(cloneUrl.trim())}`)} disabled={!cloneUrl.trim()}>
                    Continue to Clone <ArrowRight size={18} />
                  </button>
                </div>
              )}

              {repoMode === 'recent' && (
                <div className={styles.repoForm}>
                  <p>Recent projects appear after you open a trusted folder. Continue to workspace to choose one.</p>
                  <button type="button" className={styles.primary} onClick={() => router.push('/workspace')}>
                    Open Workspace <ArrowRight size={18} />
                  </button>
                </div>
              )}
            </div>
          )}

          {step === 'report' && (
            <div className={styles.reportStep}>
              <div className={styles.sectionTitle}>
                <p>AI Repository Report</p>
                <h1>{repository.status === 'ready' ? pathName(repository.rootPath || repository.name || 'Repository') : 'Repository scan'}</h1>
              </div>
              <article className={styles.reportSummary} data-state={repository.status}>
                <strong>{repository.status === 'analyzing' ? 'Scanning Repository...' : repository.status === 'failed' ? 'Analysis needs attention' : 'Repository analyzed'}</strong>
                <p>{repository.summary || repository.error || 'Arceus is detecting languages, frameworks, tests, package managers, and project structure.'}</p>
                {repository.status === 'analyzing' && <i><em /></i>}
              </article>
              <div className={styles.signalGrid}>
                {detectedSignals.map(([label, value]) => (
                  <div key={label}>
                    <small>{label}</small>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
              <div className={styles.insightGrid}>
                <article>
                  <h3>Detected risks</h3>
                  <p>{repository.skippedFiles > 0 ? `${repository.skippedFiles} files skipped by repository policy.` : 'No major scan risks detected yet.'}</p>
                </article>
                <article>
                  <h3>Suggested improvements</h3>
                  <p>{repository.testCommands.length ? 'Use the detected test command as mission verification evidence.' : 'Add or document a test command so Arceus can verify changes.'}</p>
                </article>
                <article>
                  <h3>Next best action</h3>
                  <p>Describe one feature, fix, or refactor. Arceus will generate implementation strategies before changing code.</p>
                </article>
              </div>
            </div>
          )}

          {step === 'mission' && (
            <div className={styles.missionStep}>
              <div className={styles.sectionTitle}>
                <p>Mission Creation</p>
                <h1>What would you like Arceus to do?</h1>
              </div>
              <textarea value={mission} onChange={(event) => setMission(event.target.value)} placeholder='Example: "Implement Google Login"' />
              <div className={styles.examples}>
                {EXAMPLES.map((example) => (
                  <button type="button" key={example} onClick={() => setMission(example)}>{example}</button>
                ))}
              </div>
              <div className={styles.planPreview}>
                {[1, 2, 3].map((plan) => (
                  <article key={plan}>
                    <span>Strategy {plan}</span>
                    <strong>{plan === 1 ? 'Small safe patch' : plan === 2 ? 'Balanced implementation' : 'Full production path'}</strong>
                    <p>{plan === 1 ? 'Lowest risk, limited scope.' : plan === 2 ? 'Best trade-off for most missions.' : 'Broader tests, docs, and integration.'}</p>
                  </article>
                ))}
              </div>
            </div>
          )}
        </section>

        <footer className={styles.footer}>
          <button type="button" className={styles.secondary} onClick={goBack} disabled={currentStep === 0}>
            <ChevronLeft size={18} /> Back
          </button>
          {step === 'terms' ? (
            <button type="button" className={styles.primary} onClick={goNext} disabled={!canContinueFromTerms}>Accept and Continue <ArrowRight size={18} /></button>
          ) : step === 'repository' ? (
            <button type="button" className={styles.primary} onClick={() => canContinueFromRepo ? setStep('report') : setNotice('Choose or enter a repository first.')} disabled={!canContinueFromRepo}>Continue <ArrowRight size={18} /></button>
          ) : step === 'report' ? (
            <button type="button" className={styles.primary} onClick={() => setStep('mission')} disabled={repository.status === 'analyzing'}>Create Mission <ArrowRight size={18} /></button>
          ) : step === 'mission' ? (
            <button type="button" className={styles.primary} onClick={startMission} disabled={!missionText}>Analyze Mission <ArrowRight size={18} /></button>
          ) : step !== 'welcome' ? (
            <button type="button" className={styles.primary} onClick={goNext}>Continue <ArrowRight size={18} /></button>
          ) : (
            <span />
          )}
        </footer>
      </section>
    </main>
  );
}
