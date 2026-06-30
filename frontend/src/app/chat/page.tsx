'use client';

import React, { useState, useRef, useEffect } from 'react';
import AppShell from '../../components/AppShell';
import { useChatStore } from '../../store';
import { apiRequest, createApiHeaders } from '../../utils/api';
import styles from './Chat.module.css';
import { Send, Cpu, ChevronRight, ChevronDown, Check, BrainCircuit } from 'lucide-react';

export default function ChatPage() {
  const { messages, addMessage, isStreaming, streamingContent, streamingThoughts, setIsStreaming, setStreamingContent, setStreamingThoughts } = useChatStore();
  const [input, setInput] = useState('');
  const [showThoughts, setShowThoughts] = useState<Record<string, boolean>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

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
      addMessage({
        id: `mem-${Date.now()}`,
        role: 'assistant',
        content: 'Saved that response to long-term memory.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      });
    } catch {
      addMessage({
        id: `mem-err-${Date.now()}`,
        role: 'assistant',
        content: 'I could not save that memory yet. The memory service returned an error.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      });
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

    try {
      const allMessages = [...messages, userMsg];
      const headers = createApiHeaders({
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: '00000000-0000-0000-0000-000000000000',
          messages: allMessages.map(m => ({ role: m.role, content: m.content }))
        })
      });
      const response = await fetch('/api/v1/agents/chat', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          user_id: '00000000-0000-0000-0000-000000000000',
          messages: allMessages.map(m => ({ role: m.role, content: m.content }))
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
      addMessage({
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: accumulatedContent,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        thoughts: accumulatedThoughts
      });

    } catch (error) {
      console.error(error);
      addMessage({
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: 'Error: Could not connect to the agent service. Make sure backend containers are running.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      });
    } finally {
      setIsStreaming(false);
      setStreamingContent('');
      setStreamingThoughts([]);
    }
  };

  return (
    <AppShell>
      <div className={styles.chatContainer}>
        <div className={styles.chatHeader}>
          <span className={styles.chatTitle}>Chat Session</span>
          <span className={styles.badge}>Active Agent: Brain Orchestrator</span>
        </div>

        {/* CONTEXT PIN BAR */}
        <div className={styles.contextBar}>
          <span>Context Pinned:</span>
          <div className={styles.contextItem}>
            <BrainCircuit size={12} />
            <span>Launch SaaS MVP</span>
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
              <div className={styles.messageContent}>{msg.content}</div>
              
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
                {streamingContent || '●●●'}
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
