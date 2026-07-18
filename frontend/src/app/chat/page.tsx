'use client';

import React, { useState, useRef, useEffect } from 'react';
import AppShell from '../../components/AppShell';
import { useChatStore, useAppStore } from '../../store';
import { apiRequest, createApiHeadersAsync } from '../../utils/api';
import styles from './Chat.module.css';
import { Send, Cpu, ChevronRight, ChevronDown, Check, BrainCircuit, X, ImageIcon } from 'lucide-react';
import MarkdownRenderer from '../../components/MarkdownRenderer';

const MODEL_OPTIONS = [
  { id: 'arceus-fast', label: 'Arceus Fast', provider: 'registry', model: 'arceus-fast' },
  { id: 'arceus-reasoning', label: 'Arceus Reasoning', provider: 'registry', model: 'arceus-reasoning' },
  { id: 'arceus-codex', label: 'Arceus Codex', provider: 'registry', model: 'arceus-codex' },
  { id: 'arceus-local-code', label: 'Arceus Local Code', provider: 'registry', model: 'arceus-local-code' },
  { id: 'autonomus-ai-v1', label: 'Autonomus AI', provider: 'autonomus', model: 'autonomus-ai-v1' },
  { id: 'openai-gpt-5.6-sol', label: 'OpenAI GPT-5.6 Sol', provider: 'openai', model: 'gpt-5.6-sol' },
  { id: 'claude-sonnet-5', label: 'Claude Sonnet 5', provider: 'anthropic', model: 'claude-sonnet-5' },
  { id: 'gemini-3.5-flash', label: 'Gemini 3.5 Flash', provider: 'google', model: 'gemini-3.5-flash' },
  { id: 'groq-llama-3.3', label: 'Groq Llama 3.3', provider: 'groq', model: 'llama-3.3-70b-versatile' },
  { id: 'mistral-devstral', label: 'Mistral Devstral', provider: 'mistral', model: 'devstral-2512' }
] as const;

type ModelOption = typeof MODEL_OPTIONS[number];

type UploadedFile = {
  id: string;
  filename: string;
  content_type?: string;
  size_bytes?: number;
  extraction?: { chunk_count?: number; token_count?: number };
};

type UsageSummary = {
  last_24h?: { total_tokens: number; estimated_cost_usd: number };
  all_time?: { total_tokens: number; estimated_cost_usd: number };
};

const extractMediaUrls = (content: string) => {
  const urls = new Set<string>();
  const markdownMediaRegex = /!?\[[^\]]*\]\((https?:\/\/[^)]+)\)/g;
  let match: RegExpExecArray | null;
  while ((match = markdownMediaRegex.exec(content)) !== null) {
    urls.add(match[1]);
  }
  return Array.from(urls);
};

export default function ChatPage() {
  const { messages, addMessage, setMessages, isStreaming, streamingContent, streamingThoughts, setIsStreaming, setStreamingContent, setStreamingThoughts } = useChatStore();
  const { activeGoalContext, setActiveGoalContext } = useAppStore();
  const [input, setInput] = useState('');
  const [showThoughts, setShowThoughts] = useState<Record<string, boolean>>({});
  const [goals, setGoals] = useState<any[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<ModelOption['id']>('arceus-fast');
  const [trainingCaptureStatus, setTrainingCaptureStatus] = useState<Record<string, 'saved' | 'error' | 'saving'>>({});
  const [selectedFiles, setSelectedFiles] = useState<UploadedFile[]>([]);
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [usageSummary, setUsageSummary] = useState<UsageSummary | null>(null);
  const [imageViewer, setImageViewer] = useState<{
    url: string;
    alt: string;
    explanation: string;
    isLoading: boolean;
    error: string | null;
  } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeGoalId = activeGoalContext?.id || 'default';
  const selectedModel = MODEL_OPTIONS.find((option) => option.id === selectedModelId) || MODEL_OPTIONS[0];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

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
    const handoffPrompt = sessionStorage.getItem('interview_to_chat_prompt');
    if (handoffPrompt) {
      setInput(handoffPrompt);
      sessionStorage.removeItem('interview_to_chat_prompt');
    }
    const handoffFiles = sessionStorage.getItem('interview_to_chat_files');
    if (handoffFiles) {
      try {
        const parsedFiles = JSON.parse(handoffFiles);
        if (Array.isArray(parsedFiles)) {
          setSelectedFiles((current) => {
            const existingIds = new Set(current.map((file) => file.id));
            const incoming = parsedFiles.filter((file: UploadedFile) => file?.id && !existingIds.has(file.id));
            return [...current, ...incoming];
          });
        }
      } catch {}
      sessionStorage.removeItem('interview_to_chat_files');
    }
  }, []);

  const loadUsageSummary = async () => {
    try {
      const data = await apiRequest('/api/v1/usage/summary');
      setUsageSummary(data);
    } catch {
      setUsageSummary(null);
    }
  };

  useEffect(() => {
    loadUsageSummary();
  }, []);

  // Load goals on mount
  useEffect(() => {
    const fetchGoals = async () => {
      try {
        const data = await apiRequest('/api/v1/goals', { method: 'GET' });
        if (Array.isArray(data)) {
          setGoals(data);
        }
      } catch (err) {
        console.error('Failed to fetch goals:', err);
      }
    };
    fetchGoals();
  }, []);

  // Load chat history when activeGoalId changes
  useEffect(() => {
    const loadChatHistory = async (goalId: string) => {
      const localKey = `chat_history_${goalId}`;
      const localData = localStorage.getItem(localKey);
      if (localData) {
        try {
          const parsed = JSON.parse(localData);
          setMessages(parsed);
          return;
        } catch (e) {}
      }

      // If not in local storage, fetch from backend short-term memory
      try {
        const data = await apiRequest(`/api/v1/sessions/${goalId}/memory`, {
          method: 'GET'
        });
        if (data && Array.isArray(data.events)) {
          const loadedMsgs = data.events.map((event: any, index: number) => ({
            id: `loaded-${goalId}-${index}`,
            role: event.role === 'user' ? 'user' : 'assistant',
            content: event.content,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }));
          setMessages(loadedMsgs);
          localStorage.setItem(localKey, JSON.stringify(loadedMsgs));
        } else {
          // Initialize default message
          const defaultMsg = goalId === 'default' 
            ? {
                id: 'm1',
                role: 'assistant' as const,
                content: "Hello! I'm Autonomus AI. How can I help you today?",
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
              }
            : {
                id: `m-${goalId}`,
                role: 'assistant' as const,
                content: "This is the isolated workspace chat for your goal. I've retrieved the goal definition, criteria, and tasks context to guide our discussion.",
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
              };
          setMessages([defaultMsg]);
          localStorage.setItem(localKey, JSON.stringify([defaultMsg]));
        }
      } catch (error) {
        setMessages([]);
      }
    };

    loadChatHistory(activeGoalId);
  }, [activeGoalId, setMessages]);

  const toggleThoughts = (id: string) => {
    setShowThoughts((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const saveMessageToMemory = async (content: string) => {
    if (!content.trim()) return;
    try {
      await apiRequest('/api/v1/memories', {
        method: 'POST',
        body: JSON.stringify({
          content,
          type: 'fact',
          memory_type: 'chat_note',
          importance: 5,
          tags: ['chat']
        })
      });
      const infoMsg = {
        id: `mem-${Date.now()}`,
        role: 'assistant' as const,
        content: 'Saved that response to long-term memory.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      addMessage(infoMsg);
      // Persist to local storage
      const currentHistory = localStorage.getItem(`chat_history_${activeGoalId}`);
      if (currentHistory) {
        const parsed = JSON.parse(currentHistory);
        localStorage.setItem(`chat_history_${activeGoalId}`, JSON.stringify([...parsed, infoMsg]));
      }
    } catch {
      const errMsg = {
        id: `mem-err-${Date.now()}`,
        role: 'assistant' as const,
        content: 'I could not save that memory yet. The memory service returned an error.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      addMessage(errMsg);
      const currentHistory = localStorage.getItem(`chat_history_${activeGoalId}`);
      if (currentHistory) {
        const parsed = JSON.parse(currentHistory);
        localStorage.setItem(`chat_history_${activeGoalId}`, JSON.stringify([...parsed, errMsg]));
      }
    }
  };

  const captureTrainingExample = async (assistantMsg: any, index: number) => {
    const previousUser = [...messages.slice(0, index)].reverse().find((msg) => msg.role === 'user');
    if (!previousUser) return;

    setTrainingCaptureStatus((prev) => ({ ...prev, [assistantMsg.id]: 'saving' }));
    try {
      await apiRequest('/api/v1/training/examples', {
        method: 'POST',
        body: JSON.stringify({
          user_request: previousUser.content,
          assistant_response: assistantMsg.content,
          goal_context: activeGoalContext || null,
          selected_model: {
            label: assistantMsg.modelLabel || selectedModel.label,
            provider: assistantMsg.modelProvider || selectedModel.provider,
            model: assistantMsg.modelName || selectedModel.model,
          },
          media_urls: extractMediaUrls(assistantMsg.content),
          quality_status: 'approved',
          source: 'chat_manual_approval',
        })
      });
      setTrainingCaptureStatus((prev) => ({ ...prev, [assistantMsg.id]: 'saved' }));
    } catch (error) {
      console.error(error);
      setTrainingCaptureStatus((prev) => ({ ...prev, [assistantMsg.id]: 'error' }));
    }
  };

  const applyPromptTemplate = (kind: 'file' | 'url' | 'task' | 'goal') => {
    if (kind === 'file') {
      document.getElementById('chat-file-upload')?.click();
      return;
    }
    const templates = {
      file: 'Read file ',
      url: 'Review this URL and summarize the useful actions: ',
      task: 'Create a task for me: ',
      goal: 'Create a goal and break it into tasks: '
    };
    setInput(templates[kind]);
  };

  const uploadFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setIsUploadingFile(true);
    try {
      const uploaded: UploadedFile[] = [];
      for (const file of Array.from(files)) {
        const formData = new FormData();
        formData.append('upload', file);
        const result = await apiRequest('/api/v1/files', {
          method: 'POST',
          body: formData,
        });
        uploaded.push(result);
      }
      setSelectedFiles((current) => [...current, ...uploaded]);
      await loadUsageSummary();
    } catch (error) {
      console.error(error);
    } finally {
      setIsUploadingFile(false);
    }
  };

  const streamChatResponse = async (
    requestMessages: { role: 'user' | 'assistant'; content: string }[],
    handlers: {
      onToken?: (token: string) => void;
      onThought?: (thought: string) => void;
    } = {},
    options: { persist?: boolean } = {}
  ) => {
    const body = {
      user_id: '00000000-0000-0000-0000-000000000000',
      messages: requestMessages,
      session_id: activeGoalId,
      llm_provider: selectedModel.provider,
      llm_model: selectedModel.model,
      persist: options.persist ?? true,
      file_ids: selectedFiles.map((file) => file.id),
    };
    const headers = await createApiHeadersAsync({
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const response = await fetch('/api/v1/agents/chat', {
      method: 'POST',
      headers,
      body: JSON.stringify(body)
    });

    if (response.redirected || response.url.includes('/sign-in')) {
      throw new Error('Please sign in again before generating an answer.');
    }
    if (!response.ok) {
      const detail = await response.text().catch(() => '');
      throw new Error(detail || 'Chat request failed');
    }
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('text/html')) {
      throw new Error('The agent API returned a web page instead of an answer stream. Please sign in again or check the agent service URL.');
    }
    if (!response.body) {
      throw new Error('Chat response did not include a stream');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentEvent = '';
    let accumulatedContent = '';
    let accumulatedThoughts: string[] = [];
    let streamError = '';
    let usage: any = null;

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
          const dataStr = trimmed.slice(5).trim();
          try {
            const payload = JSON.parse(dataStr);
            if (currentEvent === 'token') {
              accumulatedContent += payload.token;
              handlers.onToken?.(accumulatedContent);
            } else if (currentEvent === 'thinking') {
              const thought = payload.node
                ? `Running node: ${payload.node} (${payload.status})`
                : `Brain execution ${payload.status}`;
              accumulatedThoughts.push(thought);
              handlers.onThought?.(thought);
            } else if (currentEvent === 'tool_start') {
              const thought = `Tool Start: ${payload.tool}`;
              accumulatedThoughts.push(thought);
              handlers.onThought?.(thought);
            } else if (currentEvent === 'tool_end') {
              const thought = `Tool End: ${payload.tool}`;
              accumulatedThoughts.push(thought);
              handlers.onThought?.(thought);
            } else if (currentEvent === 'error') {
              streamError = payload.error || 'Agent stream failed';
              throw new Error(streamError);
            } else if (currentEvent === 'done') {
              usage = payload.usage || null;
            }
          } catch (err) {
            if (currentEvent === 'error') {
              throw err;
            }
          }
        }
      }
    }

    if (streamError) {
      throw new Error(streamError);
    }
    if (!accumulatedContent.trim()) {
      throw new Error('The agent returned an empty answer. Try a different model or check the agent service logs.');
    }

    return { content: accumulatedContent, thoughts: accumulatedThoughts, usage };
  };

  const explainImage = async (image: { url: string; alt: string }) => {
    setImageViewer({
      url: image.url,
      alt: image.alt,
      explanation: '',
      isLoading: true,
      error: null,
    });

    const hiddenPrompt = [
      'Explain this image like a teacher for a student.',
      `Image URL: ${image.url}`,
      `Alt text or title: ${image.alt || 'No alt text provided.'}`,
      'Give a clear step-by-step explanation of what the student should notice, using simple language and concrete labels from the image when possible.',
      'Do not ask the student to leave the app. Do not repeat the image URL unless it is useful.'
    ].join('\n');

    try {
      await streamChatResponse(
        [
          ...messages.map((m) => ({ role: m.role, content: m.content })),
          { role: 'user', content: hiddenPrompt }
        ],
        {
          onToken: (content) => {
            setImageViewer((current) => current && current.url === image.url
              ? { ...current, explanation: content, isLoading: true, error: null }
              : current);
          }
        },
        { persist: false }
      );
      setImageViewer((current) => current && current.url === image.url
        ? { ...current, isLoading: false }
        : current);
    } catch (error) {
      setImageViewer((current) => current && current.url === image.url
        ? {
            ...current,
            isLoading: false,
            error: error instanceof Error ? error.message : 'Could not explain this image yet.'
          }
        : current);
    }
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;

    const userMsg = {
      id: `u-${Date.now()}`,
      role: 'user' as const,
      content: input,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    addMessage(userMsg);
    setInput('');
    setIsStreaming(true);
    setStreamingContent('');
    setStreamingThoughts([]);

    // Keep local storage synchronized
    const currentLocalKey = `chat_history_${activeGoalId}`;
    const previousHistory = JSON.parse(localStorage.getItem(currentLocalKey) || '[]');
    const updatedHistoryWithUser = [...previousHistory, userMsg];
    localStorage.setItem(currentLocalKey, JSON.stringify(updatedHistoryWithUser));

    try {
      let liveThoughts: string[] = [];
      const result = await streamChatResponse(
        updatedHistoryWithUser.map(m => ({ role: m.role, content: m.content })),
        {
          onToken: (content) => setStreamingContent(content),
          onThought: (thought) => {
            liveThoughts = [...liveThoughts, thought];
            setStreamingThoughts(liveThoughts);
          }
        }
      );

      // Add final assistant message to store
      const assistantMsg = {
        id: `a-${Date.now()}`,
        role: 'assistant' as const,
        content: result.content,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        thoughts: result.thoughts,
        modelLabel: selectedModel.label,
        modelProvider: selectedModel.provider,
        modelName: selectedModel.model
      };
      addMessage(assistantMsg);
      await loadUsageSummary();

      // Save complete history including assistant response to local storage
      const finalHistory = [...updatedHistoryWithUser, assistantMsg];
      localStorage.setItem(currentLocalKey, JSON.stringify(finalHistory));

    } catch (error) {
      console.error(error);
      const errMsg = {
        id: `err-${Date.now()}`,
        role: 'assistant' as const,
        content: `Error: ${error instanceof Error ? error.message : 'Could not connect to the agent service. Make sure backend containers are running.'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      addMessage(errMsg);
      // Persist error to local storage
      const finalHistoryWithError = [...updatedHistoryWithUser, errMsg];
      localStorage.setItem(currentLocalKey, JSON.stringify(finalHistoryWithError));
    } finally {
      setIsStreaming(false);
      setStreamingContent('');
      setStreamingThoughts([]);
    }
  };

  const handleGoalChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    if (val === 'default') {
      setActiveGoalContext(null);
    } else {
      const foundGoal = goals.find(g => g.id === val);
      if (foundGoal) {
        setActiveGoalContext({ id: foundGoal.id, title: foundGoal.title });
      }
    }
  };

  const assistantLabel = (modelLabel?: string) => {
    const label = modelLabel || selectedModel.label;
    return label === 'Autonomus AI' ? 'AUTONOMUS AI' : label.toUpperCase();
  };

  return (
    <AppShell>
      <div className={styles.chatContainer}>
        <div className={styles.chatHeader}>
          <span className={styles.chatTitle}>Chat Session</span>
          {usageSummary?.last_24h && (
            <span className={styles.usageBadge}>
              {usageSummary.last_24h.total_tokens.toLocaleString()} tokens today · ${usageSummary.last_24h.estimated_cost_usd.toFixed(4)}
            </span>
          )}
          <div className={styles.headerControls}>
            <div className={styles.selectorWrapper}>
              <span>Active Model:</span>
              <select
                className={styles.customSelect}
                value={selectedModelId}
                onChange={(event) => setSelectedModelId(event.target.value as ModelOption['id'])}
              >
                {MODEL_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>{option.label}</option>
                ))}
              </select>
            </div>
            <div className={styles.selectorWrapper}>
              <span>Active Goal:</span>
              <select 
                className={styles.customSelect} 
                value={activeGoalId} 
                onChange={handleGoalChange}
              >
                <option value="default">General Chat (No Goal)</option>
                {goals.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.title}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* CONTEXT PIN BAR */}
        <div className={styles.contextBar}>
          <span>Context Pinned:</span>
          <div className={styles.contextItem}>
            <BrainCircuit size={12} />
            <span>{activeGoalContext?.title || 'General Chat'}</span>
          </div>
        </div>

        {/* MESSAGE LIST */}
        <div className={styles.messageList}>
          {messages.map((msg, index) => (
            <div 
              key={msg.id} 
              className={msg.role === 'user' ? styles.messageUser : styles.messageAssistant}
              style={{ alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '85%' }}
            >
              {msg.role === 'assistant' && (
                <div className={styles.messageHeader}>
                  <Cpu size={12} color="var(--color-accent-primary)" />
                  <span>{assistantLabel(msg.modelLabel)} · {msg.timestamp}</span>
                </div>
              )}
              <div className={styles.messageContent}>
                <MarkdownRenderer content={msg.content} onExplainImage={explainImage} />
              </div>
              
              {msg.role === 'assistant' && msg.thoughts && msg.thoughts.length > 0 && (
                <>
                  <button onClick={() => toggleThoughts(msg.id)} className={styles.thoughtsToggle}>
                    {showThoughts[msg.id] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    <span>Agent Reasoning ({msg.thoughts.length} steps)</span>
                  </button>
                  {showThoughts[msg.id] && (
                    <div className={styles.thoughtsPanel}>
                      {msg.thoughts.map((thought, i) => (
                        <div key={i} className={styles.thoughtLine}>
                          <span className={styles.thoughtDot} />
                          <span>{thought}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <button className={styles.saveMemoryBtn} type="button" onClick={() => saveMessageToMemory(msg.content)}>
                    <Check size={10} style={{ marginRight: '4px' }} />
                    Save to Memory
                  </button>
                  <button
                    className={styles.saveMemoryBtn}
                    type="button"
                    onClick={() => captureTrainingExample(msg, index)}
                    disabled={trainingCaptureStatus[msg.id] === 'saving' || trainingCaptureStatus[msg.id] === 'saved'}
                  >
                    <BrainCircuit size={10} style={{ marginRight: '4px' }} />
                    {trainingCaptureStatus[msg.id] === 'saved'
                      ? 'Training Saved'
                      : trainingCaptureStatus[msg.id] === 'saving'
                        ? 'Saving...'
                        : trainingCaptureStatus[msg.id] === 'error'
                          ? 'Training Failed'
                          : 'Train Autonomus'}
                  </button>
                </>
              )}
            </div>
          ))}

          {/* STREAMING RESPONSE */}
          {isStreaming && (
            <div className={styles.messageAssistant} style={{ alignSelf: 'flex-start', maxWidth: '85%' }}>
              <div className={styles.messageHeader}>
                <Cpu size={12} className={styles.pulseDot} />
                <span>{assistantLabel()} · thinking...</span>
              </div>
              <div className={styles.messageContent}>
                <MarkdownRenderer content={streamingContent || '●●●'} onExplainImage={explainImage} />
              </div>
              {streamingThoughts.length > 0 && (
                <div className={styles.thoughtsPanel}>
                  {streamingThoughts.map((thought, i) => (
                    <div key={i} className={styles.thoughtLine}>
                      <span className={styles.thoughtDot} />
                      <span>{thought}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* INPUT BOX */}
        <form onSubmit={handleSend} className={styles.inputArea}>
          {selectedFiles.length > 0 && (
            <div className={styles.fileChipRow}>
              {selectedFiles.map((file) => (
                <button
                  key={file.id}
                  type="button"
                  className={styles.fileChip}
                  onClick={() => setSelectedFiles((current) => current.filter((item) => item.id !== file.id))}
                  title="Remove file from this chat context"
                >
                  <span>{file.filename}</span>
                  {file.extraction?.token_count ? <span>{file.extraction.token_count} tokens</span> : null}
                  <X size={12} />
                </button>
              ))}
            </div>
          )}
          <div className={styles.inputRow}>
            <input
              id="chat-file-upload"
              type="file"
              multiple
              hidden
              onChange={(event) => uploadFiles(event.target.files)}
              accept=".txt,.md,.json,.csv,.py,.js,.ts,.tsx,.html,.css,.pdf,.docx,.xlsx"
            />
            <textarea
              className={styles.textInput}
              rows={2}
              placeholder="Ask anything or give me a task..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend(e);
                }
              }}
            />
            <button 
              type="submit" 
              className={`${styles.btnSend} ${(!input.trim() || isStreaming) ? styles.btnSendDisabled : ''}`}
              disabled={!input.trim() || isStreaming}
            >
              <Send size={12} />
              <span>Send</span>
            </button>
          </div>
          <div className={styles.optionsRow}>
            <button type="button" className={styles.optionBtn} onClick={() => applyPromptTemplate('file')}>{isUploadingFile ? 'Uploading...' : 'File'}</button>
            <button type="button" className={styles.optionBtn} onClick={() => applyPromptTemplate('url')}>URL</button>
            <button type="button" className={styles.optionBtn} onClick={() => applyPromptTemplate('task')}>Task</button>
            <button type="button" className={styles.optionBtn} onClick={() => applyPromptTemplate('goal')}>Goal</button>
          </div>
        </form>
        {imageViewer && (
          <div className={styles.imageViewerOverlay} role="dialog" aria-modal="true" aria-label="Image explanation">
            <div className={styles.imageViewer}>
              <div className={styles.imageViewerHeader}>
                <div className={styles.imageViewerTitle}>
                  <ImageIcon size={16} />
                  <span>Teacher Image Explanation</span>
                </div>
                <button
                  type="button"
                  className={styles.imageViewerClose}
                  onClick={() => setImageViewer(null)}
                  aria-label="Close image explanation"
                >
                  <X size={16} />
                </button>
              </div>
              <div className={styles.imageViewerBody}>
                <div className={styles.imagePreviewPanel}>
                  <img src={imageViewer.url} alt={imageViewer.alt} className={styles.imageViewerImg} />
                  {imageViewer.alt && <span className={styles.imageCaption}>{imageViewer.alt}</span>}
                </div>
                <div className={styles.imageExplanationPanel}>
                  {imageViewer.error ? (
                    <p className={styles.imageExplanationError}>{imageViewer.error}</p>
                  ) : (
                    <MarkdownRenderer content={imageViewer.explanation || (imageViewer.isLoading ? 'Preparing the explanation...' : '')} />
                  )}
                  {imageViewer.isLoading && (
                    <div className={styles.imageExplanationLoading}>Teaching mode is thinking...</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
