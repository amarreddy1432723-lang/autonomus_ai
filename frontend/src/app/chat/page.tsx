'use client';

import React, { useState, useRef, useEffect } from 'react';
import AppShell from '../../components/AppShell';
import { useChatStore, useAppStore } from '../../store';
import { apiRequest, createApiHeaders } from '../../utils/api';
import styles from './Chat.module.css';
import { Send, Cpu, ChevronRight, ChevronDown, Check, BrainCircuit } from 'lucide-react';
import MarkdownRenderer from '../../components/MarkdownRenderer';

const MODELS = [
  { name: 'Groq Llama 3.3', provider: 'groq', model: 'llama-3.3-70b-versatile' },
  { name: 'OpenAI GPT-4o Mini', provider: 'openai', model: 'gpt-4o-mini' },
  { name: 'Anthropic Claude 3.5', provider: 'anthropic', model: 'claude-3-5-sonnet-20241022' },
  { name: 'Google Gemini 1.5', provider: 'google', model: 'gemini-1.5-flash' },
];

export default function ChatPage() {
  const { messages, addMessage, setMessages, isStreaming, streamingContent, streamingThoughts, setIsStreaming, setStreamingContent, setStreamingThoughts } = useChatStore();
  const { activeGoalContext, setActiveGoalContext } = useAppStore();
  const [input, setInput] = useState('');
  const [showThoughts, setShowThoughts] = useState<Record<string, boolean>>({});
  const [goals, setGoals] = useState<any[]>([]);
  const [selectedModel, setSelectedModel] = useState(MODELS[0]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeGoalId = activeGoalContext?.id || 'default';

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

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

  // Load saved model on mount
  useEffect(() => {
    const saved = localStorage.getItem('my_ai_selected_model');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        const found = MODELS.find(m => m.provider === parsed.provider && m.model === parsed.model);
        if (found) setSelectedModel(found);
      } catch (e) {}
    }
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
                content: "Hello! I'm your Autonomous Personal AI Agent. How can I help you today?",
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

  const applyPromptTemplate = (kind: 'file' | 'url' | 'task' | 'goal') => {
    const templates = {
      file: 'Read file ',
      url: 'Review this URL and summarize the useful actions: ',
      task: 'Create a task for me: ',
      goal: 'Create a goal and break it into tasks: '
    };
    setInput(templates[kind]);
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
      const headers = createApiHeaders({
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: '00000000-0000-0000-0000-000000000000',
          messages: updatedHistoryWithUser.map(m => ({ role: m.role, content: m.content })),
          session_id: activeGoalId,
          llm_provider: selectedModel.provider,
          llm_model: selectedModel.model,
        })
      });
      const response = await fetch('/api/v1/agents/chat', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          user_id: '00000000-0000-0000-0000-000000000000',
          messages: updatedHistoryWithUser.map(m => ({ role: m.role, content: m.content })),
          session_id: activeGoalId,
          llm_provider: selectedModel.provider,
          llm_model: selectedModel.model,
        })
      });

      if (!response.ok) {
        throw new Error('Chat request failed');
      }

      if (!response.body) return;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = '';
      let accumulatedContent = '';
      let accumulatedThoughts: string[] = [];

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
                setStreamingContent(accumulatedContent);
              } else if (currentEvent === 'thinking') {
                const thought = payload.node 
                  ? `Running node: ${payload.node} (${payload.status})`
                  : `Brain execution ${payload.status}`;
                accumulatedThoughts.push(thought);
                setStreamingThoughts([...accumulatedThoughts]);
              } else if (currentEvent === 'tool_start') {
                accumulatedThoughts.push(`🔧 Tool Start: ${payload.tool}`);
                setStreamingThoughts([...accumulatedThoughts]);
              } else if (currentEvent === 'tool_end') {
                accumulatedThoughts.push(`✅ Tool End: ${payload.tool}`);
                setStreamingThoughts([...accumulatedThoughts]);
              }
            } catch (err) {
              // Ignore parse errors for incomplete JSON
            }
          }
        }
      }

      // Add final assistant message to store
      const assistantMsg = {
        id: `a-${Date.now()}`,
        role: 'assistant' as const,
        content: accumulatedContent,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        thoughts: accumulatedThoughts
      };
      addMessage(assistantMsg);

      // Save complete history including assistant response to local storage
      const finalHistory = [...updatedHistoryWithUser, assistantMsg];
      localStorage.setItem(currentLocalKey, JSON.stringify(finalHistory));

    } catch (error) {
      console.error(error);
      const errMsg = {
        id: `err-${Date.now()}`,
        role: 'assistant' as const,
        content: 'Error: Could not connect to the agent service. Make sure backend containers are running.',
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

  const handleModelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    const found = MODELS.find(m => m.model === val);
    if (found) {
      setSelectedModel(found);
      localStorage.setItem('my_ai_selected_model', JSON.stringify(found));
    }
  };

  return (
    <AppShell>
      <div className={styles.chatContainer}>
        <div className={styles.chatHeader}>
          <span className={styles.chatTitle}>Chat Session</span>
          <div className={styles.headerControls}>
            <div className={styles.selectorWrapper}>
              <span>Active Model:</span>
              <select 
                className={styles.customSelect} 
                value={selectedModel.model} 
                onChange={handleModelChange}
              >
                {MODELS.map((m) => (
                  <option key={m.model} value={m.model}>
                    {m.name}
                  </option>
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
          {messages.map((msg) => (
            <div 
              key={msg.id} 
              className={msg.role === 'user' ? styles.messageUser : styles.messageAssistant}
              style={{ alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '85%' }}
            >
              {msg.role === 'assistant' && (
                <div className={styles.messageHeader}>
                  <Cpu size={12} color="var(--color-accent-primary)" />
                  <span>PERSONAL AI · {msg.timestamp}</span>
                </div>
              )}
              <div className={styles.messageContent}>
                <MarkdownRenderer content={msg.content} />
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
                </>
              )}
            </div>
          ))}

          {/* STREAMING RESPONSE */}
          {isStreaming && (
            <div className={styles.messageAssistant} style={{ alignSelf: 'flex-start', maxWidth: '85%' }}>
              <div className={styles.messageHeader}>
                <Cpu size={12} className={styles.pulseDot} />
                <span>PERSONAL AI · thinking...</span>
              </div>
              <div className={styles.messageContent}>
                <MarkdownRenderer content={streamingContent || '●●●'} />
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
          <div className={styles.inputRow}>
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
            <button type="button" className={styles.optionBtn} onClick={() => applyPromptTemplate('file')}>File</button>
            <button type="button" className={styles.optionBtn} onClick={() => applyPromptTemplate('url')}>URL</button>
            <button type="button" className={styles.optionBtn} onClick={() => applyPromptTemplate('task')}>Task</button>
            <button type="button" className={styles.optionBtn} onClick={() => applyPromptTemplate('goal')}>Goal</button>
          </div>
        </form>
      </div>
    </AppShell>
  );
}
