'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Bot, Clipboard, Copy, Eraser, FileText, Mic, MicOff, Pause, Save, Send, Upload, X } from 'lucide-react';
import AppShell from '../../components/AppShell';
import MarkdownRenderer from '../../components/MarkdownRenderer';
import { apiRequest, createApiHeadersAsync } from '../../utils/api';
import styles from './Interview.module.css';

const MODEL_OPTIONS = [
  { id: 'autonomus-ai-v1', label: 'Autonomus AI', provider: 'autonomus', model: 'autonomus-ai-v1' },
  { id: 'groq-llama-3.3', label: 'Groq Llama 3.3', provider: 'groq', model: 'llama-3.3-70b-versatile' },
  { id: 'openai-gpt-4o-mini', label: 'OpenAI GPT-4o mini', provider: 'openai', model: 'gpt-4o-mini' },
  { id: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash', provider: 'google', model: 'gemini-1.5-flash' }
] as const;

type ModelOption = typeof MODEL_OPTIONS[number];
type MicState = 'idle' | 'listening' | 'paused' | 'unsupported' | 'permission-denied' | 'error';
type TurnState = 'waiting_for_question' | 'question_detected' | 'listening_to_candidate_answer' | 'generating_feedback' | 'ready_for_next_question';
type CaptureTarget = 'question' | 'answer';

type InterviewTurn = {
  id: string;
  question: string;
  candidateAnswer: string;
  coaching: string;
  createdAt: string;
  resumeFilename?: string;
};

type UploadedResume = {
  id: string;
  filename: string;
  content_type?: string;
  size_bytes?: number;
  extraction?: { chunk_count?: number; token_count?: number; candidate_profile_stored?: boolean };
  metadata?: {
    candidate_profile?: { status?: string };
    token_count?: number;
    chunk_count?: number;
  };
};

type CandidateMemory = {
  id?: string;
  content: string;
  memory_type?: string;
  type?: string;
  importance?: number;
  score?: number;
  tags?: string[];
};

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onend: (() => void) | null;
};

export default function InterviewPage() {
  const router = useRouter();
  const [selectedModelId, setSelectedModelId] = useState<ModelOption['id']>('autonomus-ai-v1');
  const [goals, setGoals] = useState<any[]>([]);
  const [selectedGoalId, setSelectedGoalId] = useState('interview');
  const [micState, setMicState] = useState<MicState>('idle');
  const [isGenerating, setIsGenerating] = useState(false);
  const [turnState, setTurnState] = useState<TurnState>('waiting_for_question');
  const [captureTarget, setCaptureTarget] = useState<CaptureTarget>('question');
  const [questionTranscript, setQuestionTranscript] = useState('');
  const [answerTranscript, setAnswerTranscript] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [manualPrompt, setManualPrompt] = useState('');
  const [currentQuestion, setCurrentQuestion] = useState('');
  const [currentCoaching, setCurrentCoaching] = useState('');
  const [history, setHistory] = useState<InterviewTurn[]>([]);
  const [statusText, setStatusText] = useState('Ready to listen');
  const [resume, setResume] = useState<UploadedResume | null>(null);
  const [isUploadingResume, setIsUploadingResume] = useState(false);
  const [targetRole, setTargetRole] = useState('');
  const [targetCompany, setTargetCompany] = useState('');
  const [projectNotes, setProjectNotes] = useState('');
  const [candidateMemories, setCandidateMemories] = useState<CandidateMemory[]>([]);
  const [isLoadingMemories, setIsLoadingMemories] = useState(false);
  const [companyPrep, setCompanyPrep] = useState('');
  const [isPreparingCompany, setIsPreparingCompany] = useState(false);
  const [projectDetailDraft, setProjectDetailDraft] = useState('');

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const shouldListenRef = useRef(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const currentQuestionRef = useRef('');
  const questionTranscriptRef = useRef('');
  const answerTranscriptRef = useRef('');
  const captureTargetRef = useRef<CaptureTarget>('question');
  const historyRef = useRef<InterviewTurn[]>([]);
  const resumeRef = useRef<UploadedResume | null>(null);
  const targetRoleRef = useRef('');
  const targetCompanyRef = useRef('');
  const projectNotesRef = useRef('');
  const candidateMemoriesRef = useRef<CandidateMemory[]>([]);
  const companyPrepRef = useRef('');
  const selectedModelRef = useRef<ModelOption>(MODEL_OPTIONS[0]);
  const selectedGoalIdRef = useRef('interview');

  const selectedModel = MODEL_OPTIONS.find((option) => option.id === selectedModelId) || MODEL_OPTIONS[0];
  const liveQuestion = captureTarget === 'question' && interimTranscript ? `${questionTranscript} ${interimTranscript}`.trim() : questionTranscript;
  const liveAnswer = captureTarget === 'answer' && interimTranscript ? `${answerTranscript} ${interimTranscript}`.trim() : answerTranscript;
  const transcript = [liveQuestion, liveAnswer].filter(Boolean).join('\n').trim();
  const canUseSpeech = micState !== 'unsupported';
  const hasResumeContext = Boolean(resume?.id);
  const hasCandidateProfile = Boolean(resume?.metadata?.candidate_profile || resume?.extraction?.candidate_profile_stored);

  useEffect(() => {
    const saved = localStorage.getItem('my_ai_selected_model_id');
    if (saved && MODEL_OPTIONS.some((option) => option.id === saved)) {
      setSelectedModelId(saved as ModelOption['id']);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem('my_ai_selected_model_id', selectedModelId);
  }, [selectedModelId]);

  useEffect(() => {
    questionTranscriptRef.current = questionTranscript;
  }, [questionTranscript]);

  useEffect(() => {
    answerTranscriptRef.current = answerTranscript;
  }, [answerTranscript]);

  useEffect(() => {
    captureTargetRef.current = captureTarget;
  }, [captureTarget]);

  useEffect(() => {
    historyRef.current = history;
  }, [history]);

  useEffect(() => {
    resumeRef.current = resume;
  }, [resume]);

  useEffect(() => {
    targetRoleRef.current = targetRole;
  }, [targetRole]);

  useEffect(() => {
    targetCompanyRef.current = targetCompany;
  }, [targetCompany]);

  useEffect(() => {
    projectNotesRef.current = projectNotes;
  }, [projectNotes]);

  useEffect(() => {
    candidateMemoriesRef.current = candidateMemories;
  }, [candidateMemories]);

  useEffect(() => {
    companyPrepRef.current = companyPrep;
  }, [companyPrep]);

  useEffect(() => {
    selectedModelRef.current = selectedModel;
  }, [selectedModel]);

  useEffect(() => {
    selectedGoalIdRef.current = selectedGoalId;
  }, [selectedGoalId]);

  useEffect(() => {
    const fetchGoals = async () => {
      try {
        const data = await apiRequest('/api/v1/goals', { method: 'GET' });
        if (Array.isArray(data)) setGoals(data);
      } catch {
        setGoals([]);
      }
    };
    fetchGoals();
  }, []);

  useEffect(() => {
    const SpeechRecognitionCtor =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
      setMicState('unsupported');
      setStatusText('Speech recognition is not supported in this browser. Use the manual transcript box.');
      return;
    }

    const recognition: SpeechRecognitionLike = new SpeechRecognitionCtor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
    recognition.onresult = (event: any) => {
      let finalChunk = '';
      let interimChunk = '';
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const text = result[0]?.transcript || '';
        if (result.isFinal) finalChunk += text;
        else interimChunk += text;
      }

      if (finalChunk.trim()) {
        if (captureTargetRef.current === 'question') {
          setQuestionTranscript((current) => `${current} ${finalChunk}`.trim());
        } else {
          setAnswerTranscript((current) => `${current} ${finalChunk}`.trim());
        }
      }
      setInterimTranscript(interimChunk.trim());
    };
    recognition.onerror = (event: any) => {
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        setMicState('permission-denied');
        setStatusText('Microphone permission was denied.');
        shouldListenRef.current = false;
      } else {
        setMicState('error');
        setStatusText(`Speech recognition error: ${event.error || 'unknown error'}`);
      }
    };
    recognition.onend = () => {
      if (shouldListenRef.current) {
        try {
          recognition.start();
        } catch {
          setMicState('error');
          setStatusText('Could not restart listening.');
        }
      }
    };
    recognitionRef.current = recognition;

    return () => {
      shouldListenRef.current = false;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      abortRef.current?.abort();
      recognition.abort();
    };
    // finalTranscript is intentionally excluded; result handling uses state setters plus latest event text.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const normalizeQuestion = (value: string) => value.replace(/\s+/g, ' ').trim();

  const buildMemoryQuery = (question: string, candidateAnswer = '') => [
    question,
    candidateAnswer,
    targetRoleRef.current,
    targetCompanyRef.current,
    projectNotesRef.current,
    'interview resume project experience'
  ].filter(Boolean).join(' ');

  const refreshCandidateMemories = async (question: string, candidateAnswer = '') => {
    const query = normalizeQuestion(buildMemoryQuery(question, candidateAnswer));
    if (!query) return [];
    setIsLoadingMemories(true);
    try {
      const results = await apiRequest(`/api/v1/memories/search?query=${encodeURIComponent(query)}&limit=6`);
      const memories = Array.isArray(results) ? results.slice(0, 6) : [];
      setCandidateMemories(memories);
      candidateMemoriesRef.current = memories;
      return memories;
    } catch {
      setCandidateMemories([]);
      candidateMemoriesRef.current = [];
      return [];
    } finally {
      setIsLoadingMemories(false);
    }
  };

  const prepareCompanyContext = async () => {
    const company = normalizeQuestion(targetCompanyRef.current);
    if (!company) {
      setStatusText('Add a company name before preparing company context.');
      return;
    }
    setIsPreparingCompany(true);
    setCompanyPrep('');
    setStatusText(`Preparing ${company} interview context`);

    const prompt = [
      'Prepare concise interview context for a candidate.',
      `Company: ${company}`,
      targetRoleRef.current.trim() ? `Target role: ${targetRoleRef.current.trim()}` : '',
      'Use current web context if available. Include recent company focus areas, likely interview themes, commonly asked questions for this role/company, and what the candidate should emphasize from their resume.',
      'Keep it compact and practical. Do not invent exact interview questions; label likely questions as likely/common.',
    ].filter(Boolean).join('\n');

    const controller = new AbortController();
    try {
      const prep = await streamInterviewAnswer(prompt, controller.signal, (content) => {
        setCompanyPrep(content);
        companyPrepRef.current = content;
      });
      setCompanyPrep(prep);
      companyPrepRef.current = prep;
      setStatusText('Company context prepared');
    } catch (error) {
      setCompanyPrep('');
      companyPrepRef.current = '';
      setStatusText(error instanceof Error ? error.message : 'Company preparation failed');
    } finally {
      setIsPreparingCompany(false);
    }
  };

  const generateCoaching = async (question: string, candidateAnswer: string) => {
    const normalized = normalizeQuestion(question);
    const normalizedAnswer = normalizeQuestion(candidateAnswer);
    if (normalized.length < 8 || normalizedAnswer.length < 8) {
      setStatusText('Capture both the interviewer question and your answer first.');
      return;
    }
    const activeResume = resumeRef.current;
    if (!activeResume?.id) {
      setStatusText('Upload a resume before generating interview answers.');
      return;
    }

    currentQuestionRef.current = normalized;
    setCurrentQuestion(normalized);
    setTurnState('generating_feedback');
    setStatusText('Generating feedback and improved answer');
    setIsGenerating(true);
    setCurrentCoaching('');
    const relevantMemories = candidateMemoriesRef.current.slice(0, 6);
    void refreshCandidateMemories(normalized, normalizedAnswer);

    const hiddenPrompt = [
      'You are Autonomus AI in real interview coach mode.',
      'The user has heard an interviewer question and then gave their own spoken answer.',
      'Use the interviewer question, the candidate answer, uploaded resume, saved memories, prepared company context, project notes, and recent turns to produce coaching.',
      'Prefer evidence from resume, project notes, saved candidate memories, recent Q&A, and company prep before using general interview structure.',
      'Do not invent exact companies, metrics, technologies, or project details not present in the resume. If detail is missing, give safe wording and briefly mark what detail should be filled in later.',
      'Return markdown with exactly these sections: **Improved Answer**, **What Was Good**, **Missing Points To Add**, **Possible Follow-Up**.',
      'The Improved Answer must be first person, interview-ready, concise, and grounded in resume/projects.',
      'For behavioral questions, improve the answer with STAR. For technical/project questions, include stack, contribution, tradeoffs, and impact when available.',
      targetRoleRef.current.trim() ? `Target role: ${targetRoleRef.current.trim()}` : '',
      targetCompanyRef.current.trim() ? `Target company: ${targetCompanyRef.current.trim()}` : '',
      projectNotesRef.current.trim() ? `Additional project notes from candidate: ${projectNotesRef.current.trim()}` : '',
      activeResume.filename ? `Resume file in context: ${activeResume.filename}` : '',
      relevantMemories.length
        ? `Relevant saved candidate memories:\n${relevantMemories.map((memory, index) => `${index + 1}. ${memory.content}`).join('\n')}`
        : '',
      companyPrepRef.current.trim() ? `Prepared company/interview context:\n${companyPrepRef.current.trim()}` : '',
      historyRef.current.length
        ? `Recent interview turns:\n${historyRef.current.slice(0, 5).map((turn, index) => `${index + 1}. Q: ${turn.question}\nCandidate answer: ${turn.candidateAnswer}\nCoach output: ${turn.coaching}`).join('\n\n')}`
        : '',
      '',
      `Interviewer question: ${normalized}`,
      `Candidate answer: ${normalizedAnswer}`,
    ].filter(Boolean).join('\n');

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const coaching = await streamInterviewAnswer(hiddenPrompt, controller.signal, (content) => {
        if (currentQuestionRef.current === normalized) setCurrentCoaching(content);
      });
      if (!controller.signal.aborted && currentQuestionRef.current === normalized) {
        setHistory((items) => [
          {
            id: `${Date.now()}`,
            question: normalized,
            candidateAnswer: normalizedAnswer,
            coaching,
            createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            resumeFilename: activeResume.filename,
          },
          ...items,
        ].slice(0, 8));
        setTurnState('ready_for_next_question');
        setStatusText('Coaching ready');
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setCurrentCoaching(`Error: ${error instanceof Error ? error.message : 'Could not generate answer.'}`);
        setStatusText('Answer generation failed');
      }
    } finally {
      if (!controller.signal.aborted) {
        setIsGenerating(false);
      }
    }
  };

  const streamInterviewAnswer = async (
    prompt: string,
    signal: AbortSignal,
    onToken: (content: string) => void,
  ) => {
    const body = {
      user_id: '00000000-0000-0000-0000-000000000000',
      messages: [{ role: 'user', content: prompt }],
      session_id: selectedGoalIdRef.current,
      llm_provider: selectedModelRef.current.provider,
      llm_model: selectedModelRef.current.model,
      persist: false,
      file_ids: resumeRef.current?.id ? [resumeRef.current.id] : [],
    };
    const headers = await createApiHeadersAsync({
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const response = await fetch('/api/v1/agents/chat', {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal,
    });
    if (response.redirected || response.url.includes('/sign-in')) {
      throw new Error('Please sign in again before generating interview answers.');
    }
    if (!response.ok) {
      const detail = await response.text().catch(() => '');
      throw new Error(detail || 'Interview answer request failed');
    }
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('text/html')) {
      throw new Error('The agent API returned a web page instead of an answer stream. Please sign in again or check the agent service URL.');
    }
    if (!response.body) throw new Error('Interview answer stream was empty');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentEvent = '';
    let accumulated = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('event:')) {
          currentEvent = trimmed.slice(6).trim();
        } else if (trimmed.startsWith('data:')) {
          let payload: { token?: string; error?: string };
          try {
            payload = JSON.parse(trimmed.slice(5).trim());
          } catch {
            continue;
          }
          if (currentEvent === 'token') {
            accumulated += payload.token || '';
            onToken(accumulated);
          } else if (currentEvent === 'error') {
            throw new Error(payload.error || 'Agent stream failed');
          }
        }
      }
    }

    if (!accumulated.trim()) {
      throw new Error('The agent returned an empty answer. Try a different model or check the agent service logs.');
    }

    return accumulated;
  };

  const startListening = () => {
    if (!hasResumeContext) {
      setStatusText('Upload your resume before starting.');
      return;
    }
    if (!recognitionRef.current) {
      setMicState('unsupported');
      return;
    }
    shouldListenRef.current = true;
    setMicState('listening');
    setCaptureTarget('question');
    captureTargetRef.current = 'question';
    setTurnState('waiting_for_question');
    setStatusText('Listening for interviewer question');
    try {
      recognitionRef.current.start();
    } catch {
      setStatusText('Listening is already active');
    }
  };

  const pauseListening = () => {
    shouldListenRef.current = false;
    recognitionRef.current?.stop();
    if (debounceRef.current) clearTimeout(debounceRef.current);
    abortRef.current?.abort();
    setIsGenerating(false);
    setMicState('paused');
    setStatusText('Paused');
  };

  const clearSession = () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    abortRef.current?.abort();
    setQuestionTranscript('');
    setAnswerTranscript('');
    setInterimTranscript('');
    setManualPrompt('');
    setCurrentQuestion('');
    setCurrentCoaching('');
    setHistory([]);
    currentQuestionRef.current = '';
    questionTranscriptRef.current = '';
    answerTranscriptRef.current = '';
    setIsGenerating(false);
    setCaptureTarget('question');
    captureTargetRef.current = 'question';
    setTurnState('waiting_for_question');
    setStatusText(shouldListenRef.current ? 'Listening for interviewer question' : 'Ready to listen');
  };

  const submitManualPrompt = () => {
    const value = normalizeQuestion(manualPrompt);
    if (!value) return;
    if (!hasResumeContext) {
      setStatusText('Upload your resume before generating answers.');
      return;
    }
    if (captureTarget === 'question') {
      setQuestionTranscript((current) => {
        const next = `${current} ${value}`.trim();
        questionTranscriptRef.current = next;
        return next;
      });
    } else {
      setAnswerTranscript((current) => {
        const next = `${current} ${value}`.trim();
        answerTranscriptRef.current = next;
        return next;
      });
    }
    setManualPrompt('');
  };

  const markAsQuestion = () => {
    const question = normalizeQuestion(liveQuestion);
    if (!question) {
      setStatusText('Capture or type the interviewer question first.');
      return;
    }
    setQuestionTranscript(question);
    questionTranscriptRef.current = question;
    setCurrentQuestion(question);
    currentQuestionRef.current = question;
    setInterimTranscript('');
    setTurnState('question_detected');
    setStatusText('Question captured. Start your answer when ready.');
    void refreshCandidateMemories(question);
  };

  const startMyAnswer = () => {
    if (!normalizeQuestion(questionTranscriptRef.current || liveQuestion)) {
      setStatusText('Mark the interviewer question before answering.');
      return;
    }
    setCaptureTarget('answer');
    captureTargetRef.current = 'answer';
    setInterimTranscript('');
    setTurnState('listening_to_candidate_answer');
    setStatusText('Listening to your answer');
  };

  const finishMyAnswer = () => {
    const answer = normalizeQuestion(liveAnswer);
    if (!answer) {
      setStatusText('Capture your answer before generating coaching.');
      return;
    }
    setAnswerTranscript(answer);
    answerTranscriptRef.current = answer;
    setInterimTranscript('');
    setTurnState('ready_for_next_question');
    setStatusText('Answer captured. Generate coaching when ready.');
    void refreshCandidateMemories(questionTranscriptRef.current || liveQuestion, answer);
  };

  const generateCurrentCoaching = () => {
    const question = normalizeQuestion(questionTranscriptRef.current || liveQuestion);
    const answer = normalizeQuestion(answerTranscriptRef.current || liveAnswer);
    void generateCoaching(question, answer);
  };

  const nextQuestion = () => {
    abortRef.current?.abort();
    setQuestionTranscript('');
    setAnswerTranscript('');
    setInterimTranscript('');
    setManualPrompt('');
    setCurrentQuestion('');
    setCurrentCoaching('');
    currentQuestionRef.current = '';
    questionTranscriptRef.current = '';
    answerTranscriptRef.current = '';
    setIsGenerating(false);
    setCaptureTarget('question');
    captureTargetRef.current = 'question';
    setTurnState('waiting_for_question');
    setStatusText(shouldListenRef.current ? 'Listening for next interviewer question' : 'Ready for next question');
  };

  const uploadResume = async (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    setIsUploadingResume(true);
    setStatusText('Uploading and extracting resume');
    try {
      const formData = new FormData();
      formData.append('upload', file);
      const result = await apiRequest('/api/v1/files', {
        method: 'POST',
        body: formData,
      });
      resumeRef.current = result;
      setResume(result);
      setStatusText(result?.metadata?.candidate_profile ? 'Candidate profile stored' : 'Resume context active');
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : 'Resume upload failed');
    } finally {
      setIsUploadingResume(false);
    }
  };

  const removeResume = () => {
    pauseListening();
    resumeRef.current = null;
    setResume(null);
    setStatusText('Resume removed. Upload a resume to continue.');
  };

  const copyAnswer = async () => {
    if (!currentCoaching.trim()) return;
    await navigator.clipboard.writeText(currentCoaching);
    setStatusText('Answer copied');
  };

  const saveAnswer = async () => {
    if (!currentQuestion.trim() || !currentCoaching.trim()) return;
    await apiRequest('/api/v1/memories', {
      method: 'POST',
      body: JSON.stringify({
        content: `Interview question: ${currentQuestion}\nMy answer: ${answerTranscript}\nCoach output: ${currentCoaching}`,
        type: 'fact',
        memory_type: 'interview_note',
        importance: 5,
        tags: ['interview', 'coach', resume?.filename || 'resume'],
      }),
    });
    setStatusText('Saved to memory');
    await refreshCandidateMemories(currentQuestion, answerTranscript);
  };

  const rememberProjectDetail = async () => {
    const detail = normalizeQuestion(projectDetailDraft);
    if (!detail) return;
    await apiRequest('/api/v1/memories', {
      method: 'POST',
      body: JSON.stringify({
        content: detail,
        type: 'fact',
        memory_type: 'interview_project_detail',
        importance: 7,
        tags: ['interview', 'project', resume?.filename || 'resume'],
      }),
    });
    setProjectDetailDraft('');
    setStatusText('Project detail saved to interview memory');
    await refreshCandidateMemories(currentQuestion || questionTranscript, answerTranscript);
  };

  const sendToChat = () => {
    const payload = [
      'Continue helping me with this interview question.',
      '',
      `Question: ${currentQuestion || transcript}`,
      answerTranscript ? `My answer: ${answerTranscript}` : '',
      currentCoaching ? `Coach output: ${currentCoaching}` : '',
      history.length ? `Recent turns:\n${history.slice(0, 5).map((turn, index) => `${index + 1}. Q: ${turn.question}\nA: ${turn.candidateAnswer}\nCoach: ${turn.coaching}`).join('\n\n')}` : '',
      resume?.filename ? `Resume context: ${resume.filename}` : '',
    ].filter(Boolean).join('\n');
    sessionStorage.setItem('interview_to_chat_prompt', payload);
    if (resume) {
      sessionStorage.setItem('interview_to_chat_files', JSON.stringify([resume]));
    }
    router.push('/chat');
  };

  const statusClass = [
    styles.statusPill,
    micState === 'listening' ? styles.statusListening : '',
    isGenerating ? styles.statusGenerating : '',
    micState === 'permission-denied' || micState === 'error' || micState === 'unsupported' ? styles.statusError : '',
  ].filter(Boolean).join(' ');

  return (
    <AppShell>
      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.titleBlock}>
            <h1 className={styles.title}>Interview Assist</h1>
            <p className={styles.subtitle}>Private on-screen coaching with continuous listening and visible streaming answers.</p>
          </div>
          <div className={styles.controls}>
            <span className={statusClass}>
              <span className={styles.statusDot} />
              {isGenerating ? 'Generating' : statusText}
            </span>
            {micState === 'listening' ? (
              <button className={styles.dangerButton} type="button" onClick={pauseListening}>
                <Pause size={15} />
                Pause
              </button>
            ) : (
              <button className={styles.primaryButton} type="button" onClick={startListening} disabled={!canUseSpeech || !hasResumeContext}>
                <Mic size={15} />
                Start Listening
              </button>
            )}
            <button className={styles.button} type="button" onClick={clearSession}>
              <Eraser size={15} />
              Clear
            </button>
          </div>
        </header>

        <div className={styles.settingsRow}>
          <label className={styles.selector}>
            <span>Model</span>
            <select className={styles.select} value={selectedModelId} onChange={(event) => setSelectedModelId(event.target.value as ModelOption['id'])}>
              {MODEL_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
            </select>
          </label>
          <label className={styles.selector}>
            <span>Goal context</span>
            <select className={styles.select} value={selectedGoalId} onChange={(event) => setSelectedGoalId(event.target.value)}>
              <option value="interview">Interview Assist</option>
              {goals.map((goal) => (
                <option key={goal.id} value={goal.id}>{goal.title}</option>
              ))}
            </select>
          </label>
        </div>

        <section className={styles.setupPanel}>
          <div className={styles.setupHeader}>
            <div>
              <h2 className={styles.setupTitle}>Resume context required</h2>
              <p className={styles.setupSubtitle}>Upload your resume first. Autonomus AI will answer as you, using your resume and projects as the main source.</p>
            </div>
            <input
              id="interview-resume-upload"
              hidden
              type="file"
              accept=".pdf,.docx,.txt,.md"
              onChange={(event) => uploadResume(event.target.files)}
            />
            <button
              className={styles.primaryButton}
              type="button"
              onClick={() => document.getElementById('interview-resume-upload')?.click()}
              disabled={isUploadingResume}
            >
              <Upload size={15} />
              {isUploadingResume ? 'Uploading...' : 'Upload Resume'}
            </button>
          </div>

          {resume ? (
            <div className={styles.resumeChip}>
              <FileText size={16} />
              <span className={styles.resumeName}>{resume.filename}</span>
              <span className={styles.resumeMeta}>
                {hasCandidateProfile
                  ? 'Candidate profile stored'
                  : resume.extraction?.token_count
                    ? `${resume.extraction.token_count.toLocaleString()} tokens`
                    : 'Extracted'}
              </span>
              <button className={styles.iconOnlyButton} type="button" onClick={removeResume} aria-label="Remove resume">
                <X size={14} />
              </button>
            </div>
          ) : (
            <div className={styles.notice}>Start Listening is locked until a resume is uploaded.</div>
          )}

          <div className={styles.profileGrid}>
            <label className={styles.fieldLabel}>
              <span>Target role</span>
              <input className={styles.textField} value={targetRole} onChange={(event) => setTargetRole(event.target.value)} placeholder="Frontend Engineer, Data Analyst..." />
            </label>
            <label className={styles.fieldLabel}>
              <span>Company</span>
              <input className={styles.textField} value={targetCompany} onChange={(event) => setTargetCompany(event.target.value)} placeholder="Optional company name" />
            </label>
            <label className={`${styles.fieldLabel} ${styles.wideField}`}>
              <span>Extra project notes</span>
              <textarea className={styles.notesField} value={projectNotes} onChange={(event) => setProjectNotes(event.target.value)} placeholder="Optional: add project details, metrics, tech stack, or stories not present in the resume." />
            </label>
          </div>
          <div className={styles.setupActions}>
            <button className={styles.button} type="button" onClick={prepareCompanyContext} disabled={!targetCompany.trim() || isPreparingCompany}>
              {isPreparingCompany ? 'Preparing...' : 'Prepare Company Questions'}
            </button>
            <span className={styles.helperText}>Fetch likely company/role themes once, then reuse them for faster answers.</span>
          </div>
        </section>

        {micState === 'unsupported' && (
          <div className={styles.notice}>
            This browser does not support live speech recognition. Chrome or Edge desktop is recommended. You can still paste or type the interviewer prompt below.
          </div>
        )}

        <main className={styles.grid}>
          <section className={styles.panel}>
            <div className={styles.panelHeader}>
              <span>Conversation Capture</span>
              <MicOff size={16} />
            </div>
            <div className={styles.panelBody}>
              <div className={styles.turnStateBar}>
                <span className={styles.eyebrow}>Turn state</span>
                <span className={styles.turnStateValue}>{turnState.replaceAll('_', ' ')}</span>
              </div>

              <div className={styles.questionCard}>
                <span className={styles.eyebrow}>Interviewer Question</span>
                <div className={styles.transcriptBox}>
                  {liveQuestion ? (
                    <>
                      <span className={styles.finalText}>{questionTranscript}</span>
                      {captureTarget === 'question' && interimTranscript && <span className={styles.interimText}> {interimTranscript}</span>}
                    </>
                  ) : (
                    <span className={styles.placeholder}>Listen to or type the interviewer question here.</span>
                  )}
                </div>
              </div>

              <div className={styles.questionCard}>
                <span className={styles.eyebrow}>My Answer</span>
                <div className={styles.transcriptBox}>
                  {liveAnswer ? (
                    <>
                      <span className={styles.finalText}>{answerTranscript}</span>
                      {captureTarget === 'answer' && interimTranscript && <span className={styles.interimText}> {interimTranscript}</span>}
                    </>
                  ) : (
                    <span className={styles.placeholder}>After marking the question, start your answer and speak naturally.</span>
                  )}
                </div>
              </div>

              <div className={styles.turnControls}>
                <button className={styles.button} type="button" onClick={markAsQuestion} disabled={!hasResumeContext || !liveQuestion.trim()}>
                  Mark as Question
                </button>
                <button className={styles.button} type="button" onClick={startMyAnswer} disabled={!hasResumeContext || !questionTranscript.trim()}>
                  Start My Answer
                </button>
                <button className={styles.button} type="button" onClick={finishMyAnswer} disabled={!hasResumeContext || !liveAnswer.trim()}>
                  Finish My Answer
                </button>
                <button className={styles.primaryButton} type="button" onClick={generateCurrentCoaching} disabled={!hasResumeContext || !questionTranscript.trim() || !answerTranscript.trim() || isGenerating}>
                  Generate Coaching
                </button>
                <button className={styles.button} type="button" onClick={nextQuestion}>
                  Next Question
                </button>
              </div>

              <div className={styles.questionCard}>
                <span className={styles.eyebrow}>Manual fallback for active field: {captureTarget === 'question' ? 'Question' : 'My Answer'}</span>
                <textarea
                  className={styles.manualInput}
                  value={manualPrompt}
                  onChange={(event) => setManualPrompt(event.target.value)}
                  placeholder={captureTarget === 'question' ? 'Paste or type the interviewer question here...' : 'Paste or type your answer here...'}
                />
                <button className={styles.button} type="button" onClick={submitManualPrompt} disabled={!manualPrompt.trim() || !hasResumeContext}>
                  <Send size={14} />
                  Add To {captureTarget === 'question' ? 'Question' : 'My Answer'}
                </button>
              </div>

              <div className={styles.questionCard}>
                <span className={styles.eyebrow}>Context Used</span>
                <div className={styles.contextList}>
                  <div className={styles.contextRow}>
                    <span>Resume</span>
                    <strong>{resume?.filename || 'Not uploaded'}</strong>
                  </div>
                  <div className={styles.contextRow}>
                    <span>Stored profile</span>
                    <strong>{hasCandidateProfile ? 'Ready' : resume ? 'Building from resume' : 'Not ready'}</strong>
                  </div>
                  <div className={styles.contextRow}>
                    <span>Saved memories</span>
                    <strong>{isLoadingMemories ? 'Loading...' : `${candidateMemories.length} loaded`}</strong>
                  </div>
                  <div className={styles.contextRow}>
                    <span>Recent Q&A</span>
                    <strong>{history.length} turns</strong>
                  </div>
                  <div className={styles.contextRow}>
                    <span>Project notes</span>
                    <strong>{projectNotes.trim() ? 'Included' : 'Empty'}</strong>
                  </div>
                  <div className={styles.contextRow}>
                    <span>Company prep</span>
                    <strong>{companyPrep.trim() ? 'Ready' : targetCompany.trim() ? 'Not prepared' : 'No company'}</strong>
                  </div>
                </div>
                {candidateMemories.length > 0 && (
                  <div className={styles.memoryList}>
                    {candidateMemories.slice(0, 3).map((memory, index) => (
                      <div className={styles.memoryItem} key={memory.id || `${index}-${memory.content}`}>
                        {memory.content}
                      </div>
                    ))}
                  </div>
                )}
                {companyPrep && (
                  <div className={styles.companyPrepBox}>
                    <MarkdownRenderer content={companyPrep} />
                  </div>
                )}
              </div>
            </div>
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHeader}>
              <span>Visible Answer Coach</span>
              {hasResumeContext && <span className={styles.contextActive}>Resume context active</span>}
              <div className={styles.answerActions}>
                <button className={styles.button} type="button" onClick={copyAnswer} disabled={!currentCoaching.trim()}>
                  <Copy size={14} />
                  Copy
                </button>
                <button className={styles.button} type="button" onClick={saveAnswer} disabled={!currentCoaching.trim()}>
                  <Save size={14} />
                  Save
                </button>
                <button className={styles.button} type="button" onClick={sendToChat} disabled={!currentQuestion.trim() && !transcript.trim()}>
                  <Clipboard size={14} />
                  Chat
                </button>
              </div>
            </div>
            <div className={styles.panelBody}>
              <div className={styles.answerBox}>
                {currentCoaching ? (
                  <MarkdownRenderer content={currentCoaching} />
                ) : (
                  <span className={styles.placeholder}>Autonomus AI will generate feedback and an improved answer after you capture the interviewer question and your answer.</span>
                )}
              </div>

              <div className={styles.questionCard}>
                <span className={styles.eyebrow}>Recent Q&A</span>
                <div className={styles.historyList}>
                  {history.length === 0 && <span className={styles.placeholder}>No interview turns yet.</span>}
                  {history.map((turn) => (
                    <div key={turn.id} className={styles.historyItem}>
                      <div className={styles.historyQuestion}>
                        <Bot size={13} /> {turn.question}
                      </div>
                      {turn.resumeFilename && <div className={styles.historyMeta}>Resume: {turn.resumeFilename}</div>}
                      <div className={styles.historyAnswer}>My answer: {turn.candidateAnswer}</div>
                      <div className={styles.historyAnswer}>Coach: {turn.coaching}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className={styles.questionCard}>
                <span className={styles.eyebrow}>Remember project detail</span>
                <textarea
                  className={styles.manualInput}
                  value={projectDetailDraft}
                  onChange={(event) => setProjectDetailDraft(event.target.value)}
                  placeholder="Add a correction, metric, tech stack detail, or project story Autonomus AI should reuse later."
                />
                <button className={styles.button} type="button" onClick={rememberProjectDetail} disabled={!projectDetailDraft.trim()}>
                  Save Project Detail
                </button>
              </div>
            </div>
          </section>
        </main>
      </div>
    </AppShell>
  );
}
