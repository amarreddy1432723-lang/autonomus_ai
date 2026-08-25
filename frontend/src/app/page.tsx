import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  ClipboardCheck,
  Code2,
  FileCheck2,
  GitBranch,
  GitPullRequest,
  LockKeyhole,
  Play,
  RefreshCcw,
  Rocket,
  SearchCheck,
  ShieldCheck,
  Split,
  TerminalSquare,
  Undo2,
  Workflow,
} from 'lucide-react';
import PublicNav from './PublicNav';
import styles from './publicSite.module.css';

const missionSteps = [
  'Goal',
  'Repository analysis',
  'Three engineering plans',
  'Approve mission',
  'AI engineers execute',
  'Review changes',
  'Apply with undo',
];

const productCards = [
  {
    title: 'Repository intelligence',
    body: 'Arceus maps files, symbols, dependencies, tests, runtime evidence, and project memory before planning work.',
    icon: SearchCheck,
  },
  {
    title: 'Mission planning',
    body: 'Every request becomes a scoped mission with tasks, owners, constraints, risks, approvals, and expected proof.',
    icon: Workflow,
  },
  {
    title: 'AI engineering workforce',
    body: 'Specialists collaborate as one organization: implementers, reviewers, QA, security, and release operators.',
    icon: Bot,
  },
  {
    title: 'Evidence-first execution',
    body: 'Builds, tests, screenshots, logs, checks, and receipts make every change inspectable before it ships.',
    icon: ClipboardCheck,
  },
];

const workflow = [
  ['01', 'Describe the goal', 'Tell Arceus what you want to build, fix, or improve.'],
  ['02', 'Analyze the repository', 'The system collects source, tests, structure, history, and constraints.'],
  ['03', 'Choose a plan', 'Arceus presents engineering options with risk, effort, and verification criteria.'],
  ['04', 'Approve the mission', 'Human approval starts controlled execution with path reservations.'],
  ['05', 'Review evidence', 'Receipts show files changed, checks run, screenshots, failures, and rollback.'],
  ['06', 'Ship or undo', 'Create a PR, deploy a preview, or revert the mission safely.'],
];

const features: Array<[string, string, LucideIcon]> = [
  ['Desktop terminal', 'Run commands locally inside the trusted folder.', TerminalSquare],
  ['Patch rollback', 'Undo safe changes from the work receipt.', Undo2],
  ['Review gates', 'Hold risky deletes, renames, conflicts, PRs, and deploys for approval.', ShieldCheck],
  ['GitHub PR flow', 'Commit approved changes and monitor checks from the workspace.', GitPullRequest],
  ['Model routing', 'Select cloud or local models based on task type and cost.', Split],
  ['Preview proof', 'Capture screenshots, console errors, blank pages, and verification output.', FileCheck2],
  ['Persistent missions', 'Resume runtime state after restart without duplicating tool actions.', RefreshCcw],
  ['Security controls', 'Apply role boundaries, audit decisions, and scoped credentials.', LockKeyhole],
  ['Release readiness', 'Block launch until build, auth, billing, observability, and artifacts are ready.', Rocket],
];

const comparison = [
  ['Primary unit', 'Engineering mission', 'Chat or editor request', 'Code completion', 'Terminal task'],
  ['Planning', 'Structured mission plan', 'Inline planning', 'Limited', 'Prompt-driven'],
  ['Execution proof', 'Receipts, evidence, rollback', 'Diffs and chat', 'Code suggestions', 'Command output'],
  ['Review model', 'Implementers plus independent reviewers', 'Human review', 'Human review', 'Human review'],
  ['Desktop local control', 'Folder, terminal, checks, preview', 'Editor workspace', 'Editor workspace', 'Terminal'],
  ['Lifecycle memory', 'Mission and repository memory', 'Conversation/project context', 'IDE context', 'Session context'],
];

const faqs = [
  ['Is Arceus Code an IDE?', 'No. The editor and terminal are tools inside a larger AI engineering organization.'],
  ['Can I use my local repository?', 'Yes. The desktop app is built around trusted folders, local terminal execution, and project memory.'],
  ['Does it auto-apply changes?', 'Low-risk create and modify changes can apply immediately with Undo. Risky actions still require review.'],
  ['Can it create pull requests?', 'That is part of the core loop: approved changes can become a branch and PR with CI status.'],
];

export default function Home() {
  return (
    <main className={styles.site}>
      <PublicNav />

      <section className={`${styles.section} ${styles.hero}`}>
        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}>Arceus Code Alpha v0.1</span>
          <h1>Build software with an AI engineering team. Plan. Review. Execute. Ship.</h1>
          <p>
            Arceus turns software requests into structured missions with repository intelligence, AI specialists, evidence,
            review gates, rollback, and pull request status.
          </p>
          <div className={styles.actions}>
            <Link className={styles.primary} href="/download">
              Download Arceus Code <ArrowRight size={17} />
            </Link>
            <Link className={styles.secondary} href="/workspace">
              View demo <Play size={16} />
            </Link>
          </div>
        </div>

        <div className={styles.flowPreview} aria-label="Animated Arceus mission flow">
          <div className={styles.flowPreviewHeader}>
            <span>Mission flow</span>
            <strong>Proof-first execution</strong>
          </div>
          <div className={styles.flowPreviewBody}>
            {missionSteps.map((step, index) => (
              <div
                className={styles.flowPreviewStep}
                key={step}
                style={{ animationDelay: `${index * 0.18}s` }}
              >
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{step}</strong>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className={`${styles.section} ${styles.trusted}`}>
        <span>Designed for teams building with</span>
        <div>
          {['Next.js', 'FastAPI', 'PostgreSQL', 'Redis', 'Docker', 'GitHub', 'Railway'].map((tool) => (
            <span key={tool}>{tool}</span>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.eyebrow}>What is Arceus</span>
          <h2>Not a chat window. Not only an editor. A mission runtime for software work.</h2>
        </div>
        <div className={styles.splitIntro}>
          <div>
            <h3>Traditional AI coding tools answer prompts.</h3>
            <p>They help write code, but the user still has to organize the work, prove safety, run checks, review changes, and remember decisions.</p>
          </div>
          <div>
            <h3>Arceus coordinates engineering missions.</h3>
            <p>It connects intent, repository context, planning, execution, evidence, review, rollback, and PR status into one reliable loop.</p>
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.eyebrow}>Product overview</span>
          <h2>The operating layer around your engineering work.</h2>
        </div>
        <div className={styles.cardGrid}>
          {productCards.map((card) => {
            const Icon = card.icon;
            return (
              <article className={styles.card} key={card.title}>
                <Icon size={22} />
                <h3>{card.title}</h3>
                <p>{card.body}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.eyebrow}>Mission workflow</span>
          <h2>Every mission moves from intent to evidence.</h2>
        </div>
        <div className={styles.timeline}>
          {workflow.map(([number, title, body]) => (
            <article className={styles.timelineItem} key={title}>
              <span>{number}</span>
              <div>
                <h3>{title}</h3>
                <p>{body}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className={`${styles.section} ${styles.previewSection}`}>
        <div className={styles.sectionHeader}>
          <span className={styles.eyebrow}>Mission Control</span>
          <h2>See what the AI engineering organization is doing.</h2>
        </div>
        <div className={styles.missionControl}>
          <div className={styles.previewCard}>
            <div className={styles.previewTop}>
              <span>Current mission</span>
              <strong>Implement order service API</strong>
            </div>
            <div className={styles.progressTrack}>
              <span style={{ width: '72%' }} />
            </div>
            <div className={styles.previewRows}>
              {['Backend engineer: implementing service', 'QA reviewer: preparing tests', 'Security reviewer: checking auth boundary'].map((row) => (
                <p key={row}><CheckCircle2 size={15} /> {row}</p>
              ))}
            </div>
          </div>
          <div className={styles.previewCard}>
            <div className={styles.previewTop}>
              <span>Work receipt</span>
              <strong>Changes applied</strong>
            </div>
            <div className={styles.fileList}>
              <p><Code2 size={15} /> order_service.py <span>+48 -6</span></p>
              <p><Code2 size={15} /> test_orders.py <span>+31 -2</span></p>
              <p><GitBranch size={15} /> branch: agent/order-service</p>
            </div>
            <Link className={styles.inlineButton} href="/workspace">Open workspace</Link>
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.eyebrow}>Desktop preview</span>
          <h2>Local control with cloud intelligence.</h2>
        </div>
        <div className={styles.desktopPreview}>
          <aside>
            <strong>Arceus Code</strong>
            {['Home', 'Workspace', 'Agents', 'Memory', 'Deployments', 'Settings'].map((item) => <span key={item}>{item}</span>)}
          </aside>
          <div>
            <div className={styles.browserBar}>Search files, code, agents, docs...</div>
            <div className={styles.editorMock}>
              <p>Workspace</p>
              <h3>Ask Arceus to plan, build, debug, or review.</h3>
              <div className={styles.commandBox}>Plan a safe fix for the failed checkout tests</div>
            </div>
          </div>
          <aside>
            <strong>Project context</strong>
            <span>Codebase: 8,432 files</span>
            <span>Database: 24 tables</span>
            <span>Tests: passing</span>
            <span>Pending changes: none</span>
          </aside>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.eyebrow}>Capabilities</span>
          <h2>Built for the complete engineering loop.</h2>
        </div>
        <div className={styles.featureGrid}>
          {features.map(([title, body, Icon]) => (
            <article className={styles.feature} key={title}>
              <Icon size={19} />
              <div>
                <h3>{title}</h3>
                <p>{body}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.eyebrow}>Comparison</span>
          <h2>Arceus is designed around proof, governance, and continuity.</h2>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.compareTable}>
            <thead>
              <tr>
                <th>Aspect</th>
                <th>Arceus Code</th>
                <th>Cursor</th>
                <th>Copilot</th>
                <th>CLI agents</th>
              </tr>
            </thead>
            <tbody>
              {comparison.map((row) => (
                <tr key={row[0]}>
                  {row.map((cell) => <td key={cell}>{cell}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={styles.section} id="pricing">
        <div className={styles.sectionHeader}>
          <span className={styles.eyebrow}>Pricing</span>
          <h2>Start locally. Scale when missions need cloud execution.</h2>
        </div>
        <div className={styles.pricingGrid}>
          {[
            ['Free', '$0', 'Local exploration, desktop setup, and basic project context.'],
            ['Pro', '$29', 'Cloud model routing, mission receipts, preview verification, and PR flow.'],
            ['Teams', '$79', 'Shared projects, policy gates, organization memory, and review workflows.'],
          ].map(([name, price, copy]) => (
            <article className={`${styles.priceCard} ${name === 'Pro' ? styles.featuredPrice : ''}`} key={name}>
              <h3>{name}</h3>
              <strong>{price}<span>/month</span></strong>
              <p>{copy}</p>
              <Link className={name === 'Pro' ? styles.primary : styles.secondary} href="/pricing">View plan</Link>
            </article>
          ))}
        </div>
        <div className={styles.enterprise}>
          <div>
            <h3>Enterprise</h3>
            <p>SSO, audit exports, private deployments, security controls, and custom model/provider governance.</p>
          </div>
          <Link className={styles.secondary} href="/enterprise">Contact sales</Link>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.eyebrow}>FAQ</span>
          <h2>Clear answers before you install.</h2>
        </div>
        <div className={styles.faqGrid}>
          {faqs.map(([question, answer]) => (
            <article className={styles.faq} key={question}>
              <h3>{question}</h3>
              <p>{answer}</p>
            </article>
          ))}
        </div>
      </section>

      <footer className={styles.footer}>
        <div>
          <strong>Arceus Code</strong>
          <span>AI engineering team for proof-first software delivery.</span>
        </div>
        <nav aria-label="Footer navigation">
          <Link href="/download">Download</Link>
          <Link href="/docs">Docs</Link>
          <Link href="/pricing">Pricing</Link>
          <Link href="/sign-in">Sign in</Link>
        </nav>
      </footer>
    </main>
  );
}
