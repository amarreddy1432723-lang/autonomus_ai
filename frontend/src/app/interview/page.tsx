'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Bot, Clipboard, Copy, Eraser, Mic, MicOff, Pause, Save, Send } from 'lucide-react';
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

type InterviewTurn = {
  id: string;
  question: string;
  answer: string;
  createdAt: string;
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
  const [finalTranscript, setFinalTranscript] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [manualPrompt, setManualPrompt] = useState('');
  const [currentQuestion, setCurrentQuestion] = useState('');
  const [currentAnswer, setCurrentAnswer] = useState('');
  const [history, setHistory] = useState<InterviewTurn[]>([]);
  const [statusText, setStatusText] = useState('Ready to listen');

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const shouldListenRef = useRef(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastProcessedRef = useRef('');
  const currentQuestionRef = useRef('');
  const finalTranscriptRef = useRef('');

  const selectedModel = MODEL_OPTIONS.find((option) => option.id === selectedModelId) || MODEL_OPTIONS[0];
  const transcript = [finalTranscript, interimTranscript].filter(Boolean).join(' ').trim();
  const canUseSpeech = micState !== 'unsupported';

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
    finalTranscriptRef.current = finalTranscript;
  }, [finalTranscript]);

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
        setFinalTranscript((current) => `${current} ${finalChunk}`.trim());
      }
      setInterimTranscript(interimChunk.trim());

      const latestText = `${finalTranscriptRef.current} ${finalChunk} ${interimChunk}`.trim();
      scheduleAnswer(latestText);
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

  const scheduleAnswer = (rawText: string) => {
    const cleaned = normalizeQuestion(rawText);
    if (!cleaned || cleaned.length < 18) return;
    if (cleaned === currentQuestionRef.current || cleaned === lastProcessedRef.current) return;
    abortRef.current?.abort();
    setIsGenerating(false);
    if (shouldListenRef.current) setStatusText('Listening for the next question');
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void processQuestion(cleaned);
    }, 900);
  };

  const normalizeQuestion = (value: string) => value.replace(/\s+/g, ' ').trim();

  const processQuestion = async (question: string) => {
    const normalized = normalizeQuestion(question);
    if (normalized.length < 18 || normalized === lastProcessedRef.current) return;

    lastProcessedRef.current = normalized;
    currentQuestionRef.current = normalized;
    setCurrentQuestion(normalized);
    setStatusText('Generating private answer');
    setIsGenerating(true);
    setCurrentAnswer('');

    const hiddenPrompt = [
      'You are Autonomus AI in private interview coach mode.',
      'The user is in a live interview and needs a visible, concise answer they can read quickly.',
      'Do not mention that you are listening. Do not ask follow-up questions unless absolutely necessary.',
      'For behavioral questions, use a compact STAR-style answer. For technical questions, use short structured bullets.',
      'Keep the answer practical, confident, and under 180 words unless the question requires code or a longer explanation.',
      '',
      `Interview question or prompt: ${normalized}`,
    ].join('\n');

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const answer = await streamInterviewAnswer(hiddenPrompt, controller.signal, (content) => {
        if (currentQuestionRef.current === normalized) setCurrentAnswer(content);
      });
      if (!controller.signal.aborted && currentQuestionRef.current === normalized) {
        setHistory((items) => [
          {
            id: `${Date.now()}`,
            question: normalized,
            answer,
            createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
          ...items,
        ].slice(0, 8));
        setStatusText(shouldListenRef.current ? 'Listening for the next question' : 'Paused');
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setCurrentAnswer(`Error: ${error instanceof Error ? error.message : 'Could not generate answer.'}`);
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
      session_id: selectedGoalId,
      llm_provider: selectedModel.provider,
      llm_model: selectedModel.model,
      persist: false,
      file_ids: [],
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
    if (!response.ok) throw new Error('Interview answer request failed');
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
          const payload = JSON.parse(trimmed.slice(5).trim());
          if (currentEvent === 'token') {
            accumulated += payload.token || '';
            onToken(accumulated);
          } else if (currentEvent === 'error') {
            throw new Error(payload.error || 'Agent stream failed');
          }
        }
      }
    }

    return accumulated;
  };

  const startListening = () => {
    if (!recognitionRef.current) {
      setMicState('unsupported');
      return;
    }
    shouldListenRef.current = true;
    setMicState('listening');
    setStatusText('Listening for interview questions');
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
    setFinalTranscript('');
    setInterimTranscript('');
    setManualPrompt('');
    setCurrentQuestion('');
    setCurrentAnswer('');
    setHistory([]);
    lastProcessedRef.current = '';
    currentQuestionRef.current = '';
    finalTranscriptRef.current = '';
    setIsGenerating(false);
    setStatusText(shouldListenRef.current ? 'Listening for interview questions' : 'Ready to listen');
  };

  const submitManualPrompt = () => {
    const value = normalizeQuestion(manualPrompt);
    if (!value) return;
    setFinalTranscript((current) => `${current} ${value}`.trim());
    setManualPrompt('');
    void processQuestion(value);
  };

  const copyAnswer = async () => {
    if (!currentAnswer.trim()) return;
    await navigator.clipboard.writeText(currentAnswer);
    setStatusText('Answer copied');
  };

  const saveAnswer = async () => {
    if (!currentQuestion.trim() || !currentAnswer.trim()) return;
    await apiRequest('/api/v1/memories', {
      method: 'POST',
      body: JSON.stringify({
        content: `Interview prompt: ${currentQuestion}\nSuggested answer: ${currentAnswer}`,
        type: 'fact',
        memory_type: 'interview_note',
        importance: 5,
        tags: ['interview', 'coach'],
      }),
    });
    setStatusText('Saved to memory');
  };

  const sendToChat = () => {
    const payload = [
      'Continue helping me with this interview question.',
      '',
      `Question: ${currentQuestion || transcript}`,
      currentAnswer ? `Current suggested answer: ${currentAnswer}` : '',
    ].filter(Boolean).join('\n');
    sessionStorage.setItem('interview_to_chat_prompt', payload);
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
              <button className={styles.primaryButton} type="button" onClick={startListening} disabled={!canUseSpeech}>
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

        {micState === 'unsupported' && (
          <div className={styles.notice}>
            This browser does not support live speech recognition. Chrome or Edge desktop is recommended. You can still paste or type the interviewer prompt below.
          </div>
        )}

        <main className={styles.grid}>
          <section className={styles.panel}>
            <div className={styles.panelHeader}>
              <span>Live Transcript</span>
              <MicOff size={16} />
            </div>
            <div className={styles.panelBody}>
              <div className={styles.transcriptBox}>
                {transcript ? (
                  <>
                    <span className={styles.finalText}>{finalTranscript}</span>
                    {interimTranscript && <span className={styles.interimText}> {interimTranscript}</span>}
                  </>
                ) : (
                  <span className={styles.placeholder}>Start listening, then ask or hear an interview question. The transcript appears here immediately.</span>
                )}
              </div>

              <div className={styles.questionCard}>
                <span className={styles.eyebrow}>Detected question</span>
                <span className={styles.questionText}>{currentQuestion || 'No interview question detected yet.'}</span>
              </div>

              <div className={styles.questionCard}>
                <span className={styles.eyebrow}>Manual fallback</span>
                <textarea
                  className={styles.manualInput}
                  value={manualPrompt}
                  onChange={(event) => setManualPrompt(event.target.value)}
                  placeholder="Paste or type the interviewer question here..."
                />
                <button className={styles.button} type="button" onClick={submitManualPrompt} disabled={!manualPrompt.trim()}>
                  <Send size={14} />
                  Generate Answer
                </button>
              </div>
            </div>
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHeader}>
              <span>Visible Answer Coach</span>
              <div className={styles.answerActions}>
                <button className={styles.button} type="button" onClick={copyAnswer} disabled={!currentAnswer.trim()}>
                  <Copy size={14} />
                  Copy
                </button>
                <button className={styles.button} type="button" onClick={saveAnswer} disabled={!currentAnswer.trim()}>
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
                {currentAnswer ? (
                  <MarkdownRenderer content={currentAnswer} />
                ) : (
                  <span className={styles.placeholder}>Autonomus AI will stream a concise private answer here after it detects a completed question.</span>
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
                      <div className={styles.historyAnswer}>{turn.answer}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>
        </main>
      </div>
    </AppShell>
  );
}
