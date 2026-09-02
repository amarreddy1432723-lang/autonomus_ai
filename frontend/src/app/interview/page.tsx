'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Copy, Download, Key, Mic, MicOff, Paperclip, Send, Settings, Sparkles, Trash2, UploadCloud, X } from 'lucide-react';
import AppShell from '../../components/AppShell';
import MarkdownRenderer from '../../components/MarkdownRenderer';
import { autoCorrectInterviewInput, getActiveProvider, getStoredApiKeys, saveApiKey, streamUniversalAnswer } from '../../utils/interviewLLM';
import styles from './Interview.module.css';

// ── Types ──────────────────────────────────────────────────
type MicState = 'idle' | 'listening' | 'paused' | 'unsupported' | 'permission-denied';

type ChatMessage = {
  id: string;
  role: 'question' | 'answer' | 'system';
  text: string;
  streaming?: boolean;
  ts: number;
};

type ResumeInfo = {
  filename: string;
  text: string;
};

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: any) => void) | null;
  onerror: ((e: any) => void) | null;
  onend: (() => void) | null;
};

// ── PDF text extractor ─────────────────────────────────────
async function extractResumeText(file: File): Promise<string> {
  const name = file.name.toLowerCase();

  // Plain text / markdown
  if (file.type === 'text/plain' || name.endsWith('.txt') || name.endsWith('.md')) {
    return file.text();
  }

  // DOCX via mammoth
  if (name.endsWith('.docx')) {
    try {
      const mammoth = await import('mammoth');
      const arrayBuffer = await file.arrayBuffer();
      const result = await mammoth.extractRawText({ arrayBuffer });
      return result.value.trim();
    } catch {
      return file.text().catch(() => '');
    }
  }

  // PDF via pdfjs-dist
  if (name.endsWith('.pdf') || file.type === 'application/pdf') {
    try {
      const pdfjs = await import('pdfjs-dist');
      // Use the bundled worker
      pdfjs.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`;

      const arrayBuffer = await file.arrayBuffer();
      const pdf = await pdfjs.getDocument({ data: arrayBuffer }).promise;
      const pages: string[] = [];
      for (let i = 1; i <= pdf.numPages; i++) {
        const page = await pdf.getPage(i);
        const content = await page.getTextContent();
        const pageText = content.items
          .map((item: any) => ('str' in item ? item.str : ''))
          .join(' ')
          .replace(/\s{3,}/g, '  ');
        pages.push(pageText);
      }
      return pages.join('\n\n').trim();
    } catch (err) {
      console.warn('pdf.js failed, falling back to byte read:', err);
      // Last resort: byte extraction
      const arrayBuffer = await file.arrayBuffer();
      const bytes = new Uint8Array(arrayBuffer);
      const raw = new TextDecoder('latin1').decode(bytes);
      const strings = raw.match(/[\x20-\x7E\n\r\t]{5,}/g) || [];
      return strings
        .filter(s => !/^\s*$/.test(s) && !/obj|endobj|stream|xref/i.test(s))
        .join(' ')
        .replace(/\s{3,}/g, '  ')
        .slice(0, 8000);
    }
  }

  return '';
}

// ── Helpers ────────────────────────────────────────────────
const uid = () => Math.random().toString(36).slice(2);

const formatTime = (ts: number) =>
  new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

const SAMPLE_QUESTIONS = [
  'Tell me about yourself',
  'Why do you want to work at Google?',
  "What's your greatest technical achievement?",
  'Describe a time you failed and what you learned',
  'How do you handle disagreement with a teammate?',
];

// ── Component ──────────────────────────────────────────────
export default function InterviewPage() {
  // Chat
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: uid(),
      role: 'system',
      text: '👋 Hi! I\'m your AI interview coach. Upload your resume & set your target role to get personalized answers. Or just start asking questions right now!',
      ts: Date.now(),
    },
  ]);
  const [input, setInput] = useState('');

  // Speech
  const [micState, setMicState] = useState<MicState>('idle');
  const [interimText, setInterimText] = useState('');
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const shouldListenRef = useRef(false);
  const speechDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const speechAccumRef = useRef('');

  // Resume
  const [resume, setResume] = useState<ResumeInfo | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  // Setup drawer
  const [setupOpen, setSetupOpen] = useState(false);
  const [targetRole, setTargetRole] = useState('');
  const [targetCompany, setTargetCompany] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const [answerStyle, setAnswerStyle] = useState('confident');
  // Master profile — user pastes ALL their data here once
  const [masterProfile, setMasterProfile] = useState('');

  // API keys modal
  const [keysOpen, setKeysOpen] = useState(false);
  const [keyInputs, setKeyInputs] = useState({ groq: '', openai: '', gemini: '' });
  const [activeProvider, setActiveProvider] = useState(getActiveProvider());

  // Generating
  const [isGenerating, setIsGenerating] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Refs
  const feedRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const historyRef = useRef<ChatMessage[]>([]);

  // ── Scroll to bottom ──────────────────────────────────────
  const scrollToBottom = useCallback(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, []);

  useEffect(() => {
    historyRef.current = messages;
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // ── Load persisted resume & settings ──────────────────────
  useEffect(() => {
    const savedText = localStorage.getItem('interview_resume_text');
    const savedName = localStorage.getItem('interview_resume_name');
    if (savedText && savedName) {
      setResume({ filename: savedName, text: savedText });
    }
    const savedRole = localStorage.getItem('interview_target_role') || '';
    const savedCompany = localStorage.getItem('interview_target_company') || '';
    const savedStyle = localStorage.getItem('interview_answer_style') || 'confident';
    const savedProfile = localStorage.getItem('interview_master_profile') || '';
    setTargetRole(savedRole);
    setTargetCompany(savedCompany);
    setAnswerStyle(savedStyle);
    setMasterProfile(savedProfile);

    // Load stored keys into input fields
    const keys = getStoredApiKeys();
    setKeyInputs({ groq: keys.groq || '', openai: keys.openai || '', gemini: keys.gemini || '' });
  }, []);

  // ── Persist settings ──────────────────────────────────────
  useEffect(() => { localStorage.setItem('interview_target_role', targetRole); }, [targetRole]);
  useEffect(() => { localStorage.setItem('interview_target_company', targetCompany); }, [targetCompany]);
  useEffect(() => { localStorage.setItem('interview_answer_style', answerStyle); }, [answerStyle]);
  useEffect(() => { localStorage.setItem('interview_master_profile', masterProfile); }, [masterProfile]);

  // ── Speech recognition setup ──────────────────────────────
  useEffect(() => {
    const Ctor = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Ctor) { setMicState('unsupported'); return; }

    const rec: SpeechRecognitionLike = new Ctor();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = 'en-US';

    rec.onresult = (e: any) => {
      let final = '';
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0]?.transcript || '';
        if (e.results[i].isFinal) final += t;
        else interim += t;
      }
      if (final.trim()) {
        speechAccumRef.current = (speechAccumRef.current + ' ' + final).trim();
        setInput(speechAccumRef.current);
        // Fast auto-submit: 1.1s of silence for near-instant responsiveness
        if (speechDebounceRef.current) clearTimeout(speechDebounceRef.current);
        speechDebounceRef.current = setTimeout(() => {
          const q = speechAccumRef.current.trim();
          if (q.length >= 4 && !isGenerating) {
            speechAccumRef.current = '';
            setInput('');
            setInterimText('');
            handleSend(q);
          }
        }, 1100);
      }
      setInterimText(interim.trim());
    };

    rec.onerror = (e: any) => {
      const err = String(e.error || '');
      if (err.includes('not-allowed') || err.includes('service-not-allowed')) {
        setMicState('permission-denied');
        shouldListenRef.current = false;
      } else if (!err.includes('aborted') && !err.includes('no-speech')) {
        setMicState('idle');
        shouldListenRef.current = false;
      }
    };

    rec.onend = () => {
      if (shouldListenRef.current) {
        try { rec.start(); } catch { /* already running */ }
      } else {
        setMicState('idle');
        setInterimText('');
      }
    };

    recognitionRef.current = rec;
    return () => {
      shouldListenRef.current = false;
      rec.abort();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Upload resume ─────────────────────────────────────────
  const uploadResume = async (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    setIsUploading(true);
    addSystemMsg('📄 Reading your resume…');
    try {
      const text = await extractResumeText(file);
      if (!text || text.length < 50) {
        addSystemMsg('⚠️ Could not extract text from this file. Try saving as .txt for best results.');
        setIsUploading(false);
        return;
      }
      const info: ResumeInfo = { filename: file.name, text };
      setResume(info);
      localStorage.setItem('interview_resume_text', text);
      localStorage.setItem('interview_resume_name', file.name);
      addSystemMsg(`✅ Resume loaded — ${Math.round(text.length / 4).toLocaleString()} words extracted from **${file.name}**. Every answer is now personalized to your background.`);
    } catch {
      addSystemMsg('❌ Resume read failed. Try a .txt or .docx version.');
    }
    setIsUploading(false);
  };

  // ── Profile Backup & Restore ──────────────────────────────
  const exportProfileBackup = () => {
    const data = {
      masterProfile,
      targetRole,
      targetCompany,
      jobDescription,
      answerStyle,
      resume,
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `interview_profile_${(targetCompany || 'google').toLowerCase()}_backup.json`;
    a.click();
    URL.revokeObjectURL(url);
    addSystemMsg('💾 Profile backup downloaded! You can import this anytime on any device.');
  };

  const importProfileBackup = (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const json = JSON.parse(e.target?.result as string);
        if (json.masterProfile !== undefined) setMasterProfile(json.masterProfile);
        if (json.targetRole !== undefined) setTargetRole(json.targetRole);
        if (json.targetCompany !== undefined) setTargetCompany(json.targetCompany);
        if (json.jobDescription !== undefined) setJobDescription(json.jobDescription);
        if (json.answerStyle !== undefined) setAnswerStyle(json.answerStyle);
        if (json.resume !== undefined) setResume(json.resume);
        addSystemMsg('✅ Profile backup successfully restored!');
      } catch (err) {
        addSystemMsg('❌ Invalid backup JSON file.');
      }
    };
    reader.readAsText(file);
  };

  // ── Add messages ──────────────────────────────────────────
  const addSystemMsg = (text: string) => {
    setMessages(prev => [...prev, { id: uid(), role: 'system', text, ts: Date.now() }]);
  };

  const addQuestionMsg = (text: string): string => {
    const id = uid();
    setMessages(prev => [...prev, { id, role: 'question', text, ts: Date.now() }]);
    return id;
  };

  const addAnswerMsg = (): string => {
    const id = uid();
    setMessages(prev => [...prev, { id, role: 'answer', text: '', streaming: true, ts: Date.now() }]);
    return id;
  };

  const updateAnswerMsg = (id: string, text: string, done = false) => {
    setMessages(prev =>
      prev.map(m => m.id === id ? { ...m, text, streaming: !done } : m)
    );
  };

  // ── Build conversation history for LLM ───────────────────
  const buildHistory = () => {
    const msgs = historyRef.current;
    const pairs: string[] = [];
    let i = 0;
    while (i < msgs.length) {
      if (msgs[i].role === 'question') {
        const q = msgs[i].text;
        const a = msgs[i + 1]?.role === 'answer' ? msgs[i + 1].text : '';
        if (q && a) pairs.push(`Q: ${q}\nA: ${a}`);
        i += 2;
      } else {
        i++;
      }
    }
    // Last 6 turns for context window efficiency
    return pairs.slice(-6).join('\n\n---\n\n');
  };

  // ── Core: send question → stream answer ───────────────────
  const handleSend = useCallback(async (questionText?: string) => {
    const rawQ = (questionText || input).trim();
    if (!rawQ || isGenerating) return;
    const q = autoCorrectInterviewInput(rawQ);
    setInput('');
    setInterimText('');
    speechAccumRef.current = '';

    addQuestionMsg(q);
    const answerId = addAnswerMsg();
    setIsGenerating(true);

    const controller = new AbortController();
    abortRef.current = controller;

    const conversationHistory = buildHistory();

    // Master profile takes priority; falls back to uploaded resume text
    const profileCtx = masterProfile.trim()
      || resume?.text
      || localStorage.getItem('interview_resume_text')
      || '';

    // Build rich prompt: history + question
    const enrichedPrompt = [
      conversationHistory ? `Previous conversation:\n${conversationHistory}` : '',
      `Now answer this question: ${q}`,
    ].filter(Boolean).join('\n\n');

    try {
      let accumulated = '';
      await streamUniversalAnswer({
        question: enrichedPrompt,
        resumeText: profileCtx,
        targetRole: targetRole || undefined,
        targetCompany: targetCompany || undefined,
        jobDescription: jobDescription || undefined,
        interviewStyle: answerStyle,
        onToken: (_, acc) => {
          accumulated = acc;
          updateAnswerMsg(answerId, acc, false);
          scrollToBottom();
        },
        signal: controller.signal,
      });
      updateAnswerMsg(answerId, accumulated, true);
    } catch (err: any) {
      if (!controller.signal.aborted) {
        updateAnswerMsg(answerId, '⚠️ Something went wrong. Please try again.', true);
      }
    }

    setIsGenerating(false);
    abortRef.current = null;
    scrollToBottom();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input, isGenerating, resume, masterProfile, targetRole, targetCompany, jobDescription, answerStyle]);

  // ── Mic controls ──────────────────────────────────────────
  const toggleMic = () => {
    if (!recognitionRef.current || micState === 'unsupported' || micState === 'permission-denied') return;
    if (micState === 'listening') {
      shouldListenRef.current = false;
      recognitionRef.current.stop();
      setMicState('idle');
      setInterimText('');
      if (speechDebounceRef.current) clearTimeout(speechDebounceRef.current);
    } else {
      shouldListenRef.current = true;
      speechAccumRef.current = '';
      setMicState('listening');
      try { recognitionRef.current.start(); } catch { /* already running */ }
    }
  };

  // ── Save API keys ─────────────────────────────────────────
  const saveKeys = () => {
    saveApiKey('groq', keyInputs.groq);
    saveApiKey('openai', keyInputs.openai);
    saveApiKey('gemini', keyInputs.gemini);
    setActiveProvider(getActiveProvider());
    setKeysOpen(false);
    addSystemMsg(`🔑 API keys saved. Using ${getActiveProvider().provider.toUpperCase()} for answers now.`);
  };

  // ── Auto-resize textarea ──────────────────────────────────
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px';
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Clear chat ────────────────────────────────────────────
  const clearChat = () => {
    abortRef.current?.abort();
    setIsGenerating(false);
    setMessages([{
      id: uid(), role: 'system',
      text: '🗑️ Chat cleared. Ready for a fresh session!',
      ts: Date.now(),
    }]);
  };

  // ── Copy answer ───────────────────────────────────────────
  const copyMessage = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
  };

  const hasKeys = Boolean(activeProvider.key);
  const canUseMic = micState !== 'unsupported' && micState !== 'permission-denied';
  const isListening = micState === 'listening';

  return (
    <AppShell>
      <div className={styles.shell}>

        {/* ── Top bar ── */}
        <div className={styles.topBar}>
          <div className={styles.botAvatar}>🤖</div>
          <div className={styles.botInfo}>
            <div className={styles.botName}>Interview AI Coach</div>
            <div className={`${styles.botStatus} ${isGenerating ? styles.thinking : styles.online}`}>
              {isGenerating ? 'Thinking…' : isListening ? '🎙 Listening…' : 'Online'}
            </div>
          </div>
          <div className={styles.topBarActions}>
            {/* Resume indicator */}
            {resume && (
              <div className={styles.iconBtn} title={resume.filename} style={{ color: '#4ade80', borderColor: 'rgba(74,222,128,0.3)', background: 'rgba(74,222,128,0.08)', fontSize: '10px', padding: '0 8px', width: 'auto', gap: '4px' }}>
                📄 {resume.filename.length > 12 ? resume.filename.slice(0, 12) + '…' : resume.filename}
              </div>
            )}
            {/* Settings */}
            <button className={`${styles.iconBtn} ${setupOpen ? styles.active : ''}`} onClick={() => setSetupOpen(o => !o)} title="Setup">
              <Settings size={15} />
            </button>
            {/* API Keys */}
            <button className={`${styles.iconBtn} ${hasKeys ? styles.active : ''}`} onClick={() => setKeysOpen(true)} title="API Keys">
              <Key size={15} />
            </button>
            {/* Clear */}
            <button className={`${styles.iconBtn} ${styles.danger}`} onClick={clearChat} title="Clear chat">
              <Trash2 size={15} />
            </button>
          </div>
        </div>

        {/* ── Setup Drawer ── */}
        <div className={`${styles.setupDrawer} ${setupOpen ? styles.open : styles.closed}`}>
          <div className={styles.setupInner}>
            <div className={styles.setupTitle}>⚙️ Interview Setup</div>

            {/* No key banner */}
            {!hasKeys && (
              <div className={styles.apiKeyBanner}>
                <Sparkles size={14} style={{ flexShrink: 0 }} />
                <span>For real AI answers personalized to your data, add a free API key (Groq is free — 100 req/day).</span>
                <span className={styles.apiKeyBannerLink} onClick={() => { setKeysOpen(true); setSetupOpen(false); }}>Add Key →</span>
              </div>
            )}

            {/* ── MASTER PROFILE ── the main "give all data" section */}
            <div className={styles.setupField} style={{ gridColumn: '1/-1' }}>
              <label className={styles.setupLabel}>
                📋 Your Full Profile <span style={{ color: '#4ade80', fontWeight: 700 }}>(paste everything here — resume, projects, skills, achievements, education, goals)</span>
              </label>
              <textarea
                className={styles.setupTextarea}
                style={{ minHeight: 160, fontSize: 12, lineHeight: 1.6, fontFamily: 'inherit' }}
                value={masterProfile}
                onChange={e => setMasterProfile(e.target.value)}
                placeholder={`Paste ALL your information here. Example:

Name: Amar Reddy
Role applying for: Software Engineer Apprentice at Google

SKILLS: Python, JavaScript, React, Node.js, SQL, Git, REST APIs

EXPERIENCE:
- Built a full-stack task management app (React + FastAPI) with 500+ users
- Automated data pipelines reducing processing time by 40%
- Led a team of 3 on a college project that won 1st place at hackathon

EDUCATION: B.Tech Computer Science, graduating 2025, CGPA 8.2

PROJECTS:
- AI chatbot using OpenAI API (2000 daily users)
- E-commerce site with payment integration (Stripe)

ACHIEVEMENTS: Google CodeJam participant, Microsoft Azure certified

ABOUT ME: I'm passionate about building products that matter...`}
              />
              {masterProfile.trim() && (
                <div style={{ fontSize: 10, color: '#4ade80', fontWeight: 700, marginTop: 4 }}>
                  ✅ {Math.round(masterProfile.trim().length / 5).toLocaleString()} words stored — bot will use this for every answer
                </div>
              )}
            </div>

            {/* Resume upload (optional when profile is filled) */}
            <div className={styles.resumeRow}>
              <div className={styles.setupLabel} style={{ marginBottom: 0 }}>
                Or upload resume file {masterProfile.trim() ? <span style={{ color: '#64748b', fontWeight: 400 }}>(optional — profile above takes priority)</span> : ''}
              </div>
              {resume ? (
                <div className={styles.resumeChip}>
                  <span className={styles.resumeChipName}>{resume.filename}</span>
                  <span style={{ fontSize: '10px', color: '#86efac', fontWeight: 700 }}>
                    ~{Math.round(resume.text.length / 4).toLocaleString()} words
                  </span>
                  <button className={styles.removeBtn} onClick={() => {
                    setResume(null);
                    localStorage.removeItem('interview_resume_text');
                    localStorage.removeItem('interview_resume_name');
                    addSystemMsg('📄 Resume removed.');
                  }}>
                    <X size={12} />
                  </button>
                </div>
              ) : (
                <label className={styles.uploadBtn} style={{ opacity: isUploading ? 0.6 : 1 }}>
                  <Paperclip size={13} />
                  {isUploading ? 'Reading…' : 'Upload (.pdf .txt .docx)'}
                  <input
                    type="file"
                    hidden
                    accept=".pdf,.txt,.md,.docx"
                    disabled={isUploading}
                    onChange={e => uploadResume(e.target.files)}
                  />
                </label>
              )}
            </div>

            <div className={styles.setupGrid}>
              <div className={styles.setupField}>
                <label className={styles.setupLabel}>Target Role</label>
                <input
                  className={styles.setupInput}
                  value={targetRole}
                  onChange={e => setTargetRole(e.target.value)}
                  placeholder="Software Engineer Apprentice"
                />
              </div>
              <div className={styles.setupField}>
                <label className={styles.setupLabel}>Company</label>
                <input
                  className={styles.setupInput}
                  value={targetCompany}
                  onChange={e => setTargetCompany(e.target.value)}
                  placeholder="Google"
                />
              </div>
              <div className={`${styles.setupField} ${styles.wideField}`}>
                <label className={styles.setupLabel}>Job Description (paste here for best results)</label>
                <textarea
                  className={styles.setupTextarea}
                  value={jobDescription}
                  onChange={e => setJobDescription(e.target.value)}
                  placeholder="Paste the job description, requirements, or interview email…"
                />
              </div>
              <div className={styles.setupField}>
                <label className={styles.setupLabel}>Answer Style</label>
                <select
                  className={styles.setupInput}
                  value={answerStyle}
                  onChange={e => setAnswerStyle(e.target.value)}
                  style={{ cursor: 'pointer' }}
                >
                  <option value="confident">Confident & Natural</option>
                  <option value="star">STAR Method</option>
                  <option value="technical">Deep Technical</option>
                  <option value="fresher">Fresher Friendly</option>
                  <option value="short">Short & Punchy</option>
                </select>
              </div>

              {/* ── Backup & Sync across devices ── */}
              <div className={`${styles.setupField} ${styles.wideField}`} style={{ marginTop: 8, display: 'flex', gap: '8px', alignItems: 'center' }}>
                <button
                  className={styles.setupInput}
                  style={{ width: 'auto', padding: '6px 12px', fontSize: '11px', display: 'inline-flex', alignItems: 'center', gap: '6px', cursor: 'pointer', background: 'rgba(255,255,255,0.06)' }}
                  onClick={exportProfileBackup}
                  title="Export full profile & settings as JSON backup"
                >
                  <Download size={13} />
                  Export Profile JSON
                </button>

                <label
                  className={styles.setupInput}
                  style={{ width: 'auto', padding: '6px 12px', fontSize: '11px', display: 'inline-flex', alignItems: 'center', gap: '6px', cursor: 'pointer', background: 'rgba(255,255,255,0.06)', marginBottom: 0 }}
                  title="Import profile backup from JSON file"
                >
                  <UploadCloud size={13} />
                  Restore Profile JSON
                  <input
                    type="file"
                    hidden
                    accept=".json"
                    onChange={e => importProfileBackup(e.target.files)}
                  />
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* ── Chat Feed ── */}
        <div className={styles.chatFeed} ref={feedRef}>
          <div className={styles.dateSep}>Today</div>

          {messages.map((msg) => (
            <div key={msg.id} className={`${styles.msg} ${styles[msg.role]}`}>
              {msg.role !== 'system' && (
                <div className={styles.msgLabel}>
                  {msg.role === 'question' ? '🎙 Interviewer' : '🤖 AI Coach'}
                </div>
              )}
              <div className={styles.bubble}>
                {msg.streaming && msg.text === '' ? (
                  <div className={styles.typing}>
                    <div className={styles.dot} />
                    <div className={styles.dot} />
                    <div className={styles.dot} />
                  </div>
                ) : (
                  <>
                    <MarkdownRenderer content={msg.text} />
                    {msg.streaming && <span className={styles.cursor} />}
                  </>
                )}
              </div>
              <div className={styles.msgMeta} style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: msg.role === 'answer' ? 'flex-end' : 'flex-start' }}>
                <span>{formatTime(msg.ts)}</span>
                {msg.role === 'answer' && !msg.streaming && msg.text && (
                  <button
                    onClick={() => copyMessage(msg.text)}
                    style={{ background: 'none', border: 'none', color: '#3f4554', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: 0 }}
                    title="Copy answer"
                  >
                    <Copy size={11} />
                  </button>
                )}
              </div>
            </div>
          ))}

          {/* Interim speech text preview */}
          {interimText && (
            <div className={`${styles.msg} ${styles.question}`}>
              <div className={styles.msgLabel}>🎙 Listening…</div>
              <div className={styles.bubble} style={{ opacity: 0.6, fontStyle: 'italic' }}>
                {interimText}
              </div>
            </div>
          )}

          {/* Sample question chips — show only if few messages */}
          {messages.length <= 2 && !isGenerating && (
            <div className={`${styles.msg} ${styles.system}`}>
              <div className={styles.bubble}>
                <div style={{ marginBottom: 8, fontSize: 12, color: '#64748b' }}>Try a sample question:</div>
                <div className={styles.chips}>
                  {SAMPLE_QUESTIONS.map(q => (
                    <button key={q} className={styles.chip} onClick={() => handleSend(q)}>
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── Input Bar ── */}
        <div className={styles.inputBar}>
          <div className={styles.inputRow}>
            {/* Mic button */}
            <button
              className={`${styles.micBtn} ${isListening ? styles.listening : ''}`}
              onClick={toggleMic}
              disabled={!canUseMic}
              title={isListening ? 'Stop listening' : 'Start voice capture'}
            >
              {isListening ? <MicOff size={18} /> : <Mic size={18} />}
            </button>

            {/* Text input */}
            <div className={styles.inputWrap}>
              <textarea
                ref={inputRef}
                className={styles.inputField}
                rows={1}
                value={input}
                onChange={handleInput}
                onKeyDown={handleKeyDown}
                placeholder={isListening ? 'Listening… (speak the interviewer question)' : 'Type an interview question or paste from JD…'}
              />
            </div>

            {/* Send / Stop button */}
            {isGenerating ? (
              <button
                className={styles.sendBtn}
                onClick={() => { abortRef.current?.abort(); setIsGenerating(false); }}
                style={{ background: 'linear-gradient(135deg, #ef4444, #dc2626)' }}
                title="Stop generating"
              >
                <X size={18} />
              </button>
            ) : (
              <button
                className={styles.sendBtn}
                onClick={() => handleSend()}
                disabled={!input.trim()}
                title="Send"
              >
                <Send size={18} />
              </button>
            )}
          </div>
          <div className={styles.inputHint}>
            {isListening
              ? '🔴 Listening — speak the interviewer question. Pauses for 2.5s → auto-sends'
              : !resume
              ? '💡 Upload your resume in Settings (⚙️) for personalized answers'
              : !hasKeys
              ? '💡 Add a free Groq API key in 🔑 for real AI answers'
              : `✓ Resume loaded · ${targetCompany || 'Set company'} · ${answerStyle} mode`}
          </div>
        </div>

      </div>

      {/* ── API Keys Modal ── */}
      {keysOpen && (
        <div className={styles.modalOverlay} onClick={() => setKeysOpen(false)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalTitle}>🔑 Add Your API Keys</div>
            <div className={styles.modalSubtitle}>
              Keys are stored only in your browser (localStorage). Never sent anywhere except directly to the AI provider.
              <br /><br />
              <strong>Groq is free</strong> — get a key in 60 seconds at{' '}
              <a href="https://console.groq.com" target="_blank" rel="noopener noreferrer" style={{ color: '#818cf8' }}>
                console.groq.com
              </a>
            </div>

            {[
              { key: 'groq', label: 'Groq (FREE · Llama 3.3 70B · Recommended)', placeholder: 'gsk_...' },
              { key: 'openai', label: 'OpenAI (GPT-4o mini)', placeholder: 'sk-...' },
              { key: 'gemini', label: 'Google Gemini (1.5 Flash)', placeholder: 'AIza...' },
            ].map(({ key, label, placeholder }) => (
              <div key={key} className={styles.modalField}>
                <label className={styles.modalLabel}>{label}</label>
                <input
                  className={styles.modalInput}
                  type="password"
                  placeholder={placeholder}
                  value={keyInputs[key as keyof typeof keyInputs]}
                  onChange={e => setKeyInputs(prev => ({ ...prev, [key]: e.target.value }))}
                />
              </div>
            ))}

            <div className={styles.modalActions}>
              <button className={styles.modalCancel} onClick={() => setKeysOpen(false)}>Cancel</button>
              <button className={styles.modalSave} onClick={saveKeys}>Save Keys</button>
            </div>
          </div>
        </div>
      )}

    </AppShell>
  );
}
