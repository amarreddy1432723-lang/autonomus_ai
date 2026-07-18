'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Bell,
  Brain,
  Check,
  ChevronRight,
  ClipboardList,
  FileText,
  Image as ImageIcon,
  Lightbulb,
  Mic,
  Paperclip,
  Settings,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  UserRound,
} from 'lucide-react';
import styles from './IdeaDiscovery.module.css';

const STAGES = ['Idea Discovery', 'Product Blueprint', 'Architecture', 'AI Team', 'Build'];

const SUGGESTIONS = [
  'Build an AI SaaS',
  'Healthcare Platform',
  'Marketplace',
  'Developer Tool',
  'AI Assistant',
  'E-commerce',
  'CRM',
  'Productivity',
  'Social Platform',
];

const INTELLIGENCE_ITEMS = [
  'Detect missing requirements',
  'Improve product ideas',
  'Recommend architecture',
  'Estimate complexity',
  'Predict development cost',
  'Suggest monetization',
  'Find security risks',
  'Recommend technologies',
];

const SUPPORT_ITEMS = [
  { label: 'Text', icon: FileText },
  { label: 'Images', icon: ImageIcon },
  { label: 'PDF', icon: ClipboardList },
  { label: 'Documents', icon: FileText },
  { label: 'Voice', icon: Mic },
  { label: 'Drag & Drop', icon: UploadCloud },
];

export default function IdeaDiscoveryPage() {
  const router = useRouter();
  const [idea, setIdea] = useState('');

  const selectedLength = idea.trim().length;
  const canContinue = selectedLength > 8;
  const placeholder = useMemo(
    () => 'I want to build an AI platform that helps developers build complete software using autonomous AI engineering teams.',
    [],
  );

  const useSuggestion = (suggestion: string) => {
    setIdea((current) => {
      const prefix = current.trim();
      if (!prefix) return `I want to build a ${suggestion.toLowerCase()} that `;
      return `${prefix}${prefix.endsWith('.') ? ' ' : '. '}Explore it as a ${suggestion.toLowerCase()}.`;
    });
  };

  const understandIdea = () => {
    const params = new URLSearchParams();
    params.set('stage', 'domain-intelligence');
    if (idea.trim()) params.set('idea', idea.trim());
    router.push(`/domain-intelligence?${params.toString()}`);
  };

  return (
    <main className={styles.discovery}>
      <section className={styles.window} aria-label="Arceus Code product discovery workspace">
        <header className={styles.topbar}>
          <div className={styles.leftNav}>
            <button type="button" className={styles.backButton} onClick={() => router.push('/launch')}>
              <ArrowLeft size={18} />
              Back
            </button>
            <div className={styles.brandBlock}>
              <strong>Arceus Code</strong>
              <span>Current Stage</span>
              <b>Idea Discovery</b>
            </div>
          </div>

          <nav className={styles.stageNav} aria-label="Product build stages">
            {STAGES.map((stage, index) => (
              <span key={stage} className={styles.stageItem} data-active={index === 0}>
                {stage}
                {index < STAGES.length - 1 ? <ChevronRight size={13} /> : null}
              </span>
            ))}
          </nav>

          <div className={styles.rightNav}>
            <button type="button" className={styles.saveDraft}>Save Draft</button>
            <button type="button" className={styles.iconButton} aria-label="Settings" onClick={() => router.push('/settings')}>
              <Settings size={18} />
            </button>
            <button type="button" className={styles.iconButton} aria-label="Notifications">
              <Bell size={18} />
            </button>
            <button type="button" className={styles.profileButton} aria-label="Profile">
              <UserRound size={18} />
            </button>
          </div>
        </header>

        <section className={styles.hero}>
          <p className={styles.eyebrow}>
            <Sparkles size={16} />
            Product Discovery
          </p>
          <h1>Let&apos;s understand your idea.</h1>
          <p>
            Describe what you want to build. The more context you provide, the better Arceus can design,
            plan and build your application.
          </p>
        </section>

        <section className={styles.contentGrid}>
          <div className={styles.ideaColumn}>
            <label className={styles.inputCard}>
              <textarea
                value={idea}
                onChange={(event) => setIdea(event.target.value)}
                placeholder={placeholder}
                rows={8}
              />
              <div className={styles.supportStrip}>
                {SUPPORT_ITEMS.map((item) => {
                  const Icon = item.icon;
                  return (
                    <span key={item.label}>
                      <Icon size={15} />
                      {item.label}
                    </span>
                  );
                })}
              </div>
            </label>

            <div className={styles.inputActions}>
              <button type="button">
                <Paperclip size={17} />
                Attach Files
              </button>
              <button type="button">
                <ClipboardList size={17} />
                Import Requirements
              </button>
              <button type="button">
                <Mic size={17} />
                Record Voice
              </button>
              <button type="button">
                <FileText size={17} />
                Paste Documentation
              </button>
            </div>

            <section className={styles.suggestions} aria-label="Product idea suggestions">
              <p>Start with a direction</p>
              <div>
                {SUGGESTIONS.map((suggestion) => (
                  <button key={suggestion} type="button" onClick={() => useSuggestion(suggestion)}>
                    {suggestion}
                  </button>
                ))}
              </div>
            </section>
          </div>

          <aside className={styles.intelligencePanel}>
            <div className={styles.panelIcon}>
              <Brain size={24} />
            </div>
            <h2>Arceus Intelligence</h2>
            <p>I&apos;ll help you create a better product.</p>
            <div className={styles.intelligenceRows}>
              {INTELLIGENCE_ITEMS.map((item) => (
                <div key={item} className={styles.intelligenceRow}>
                  <span>
                    <Check size={14} />
                  </span>
                  {item}
                </div>
              ))}
            </div>
          </aside>
        </section>

        <footer className={styles.footer}>
          <div className={styles.footerActions}>
            <button type="button" className={styles.primaryButton} onClick={understandIdea} disabled={!canContinue}>
              <Lightbulb size={20} />
              Understand My Idea
            </button>
            <button type="button" className={styles.secondaryButton}>
              <ShieldCheck size={19} />
              Guided Discovery
            </button>
          </div>
          <p>Arceus will not generate code yet. It will first understand your product.</p>
        </footer>
      </section>
    </main>
  );
}
