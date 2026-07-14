'use client';

import { useEffect, useRef, useState } from 'react';
import { Terminal as XtermTerminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { SearchAddon } from '@xterm/addon-search';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { ChevronsDown, ChevronsUp, Copy, Maximize2, Minimize2, Plus, RotateCcw, Search, Square, Terminal, Trash2, X } from 'lucide-react';
import type { TerminalSession } from './ActivityPanel';
import styles from './Workspace.module.css';

export type TerminalPanelSize = 'compact' | 'half' | 'max';

type Props = {
  open: boolean;
  size: TerminalPanelSize;
  sessions: TerminalSession[];
  activeTerminalId: string;
  command: string;
  canUseTerminal: boolean;
  helpText: string;
  busy: boolean;
  onClose: () => void;
  onSizeChange: (size: TerminalPanelSize) => void;
  onCreate: (shellProfile?: string) => void;
  onSelect: (terminalId: string) => void;
  onCommandChange: (value: string) => void;
  onSend: () => void;
  onRawInput?: (terminalId: string, input: string) => void;
  onResize?: (terminalId: string, cols: number, rows: number) => void;
  onCloudFrame?: (terminalId: string, frame: Record<string, any>) => void;
  onKill: (terminalId: string) => void;
  onRestart: (terminalId: string) => void;
  onClear: (terminalId: string) => void;
  sessionId: string;
};

function cleanTerminalText(value: string) {
  return value
    .replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, '')
    .replace(/\r(?!\n)/g, '\n');
}

function terminalOutput(terminal: TerminalSession | null) {
  if (!terminal) return '';
  return (terminal.logs || []).map((log) => {
    if (typeof log === 'string') return log;
    return String(log.output_excerpt || log.output || log.stdout || log.stderr || log.detail || '');
  }).filter(Boolean).join('');
}

function getStoredAuth() {
  if (typeof window === 'undefined') return { token: '', userId: '' };
  return {
    token: window.localStorage.getItem('my-ai.access_token') || '',
    userId: window.localStorage.getItem('my-ai.user_id') || '00000000-0000-0000-0000-000000000000',
  };
}

function terminalWebSocketUrl(sessionId: string, terminalId: string, shellProfile: string, lastByteOffset: number) {
  const base = process.env.NEXT_PUBLIC_AGENT_URL || 'http://localhost:8003';
  const url = new URL('/api/v1/terminal/pty', base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  const auth = getStoredAuth();
  url.searchParams.set('session_id', sessionId);
  url.searchParams.set('terminal_id', terminalId);
  url.searchParams.set('shell', shellProfile);
  url.searchParams.set('lastByteOffset', String(lastByteOffset || 0));
  if (auth.token) url.searchParams.set('token', auth.token);
  if (auth.userId) url.searchParams.set('user_id', auth.userId);
  return url.toString();
}

export default function WorkspaceTerminalPanel({
  open,
  size,
  sessions,
  activeTerminalId,
  command,
  canUseTerminal,
  helpText,
  busy,
  onClose,
  onSizeChange,
  onCreate,
  onSelect,
  onCommandChange,
  onSend,
  onRawInput,
  onResize,
  onCloudFrame,
  onKill,
  onRestart,
  onClear,
  sessionId,
}: Props) {
  const activeTerminal = sessions.find((terminal) => terminal.id === activeTerminalId) || sessions[0] || null;
  const rawOutput = terminalOutput(activeTerminal);
  const output = cleanTerminalText(rawOutput);
  const status = activeTerminal?.status || 'idle';
  const viewportRef = useRef<HTMLDivElement | null>(null);
  
  // Persistent multi-terminal cache
  const terminalsRef = useRef<Record<string, {
    terminal: XtermTerminal;
    fitAddon: FitAddon;
    searchAddon: SearchAddon;
    socket: WebSocket | null;
    lastRawOutputLength: number;
    lastResize?: { cols: number; rows: number };
  }>>({});

  const pendingCloudFramesRef = useRef<string[]>([]);
  const cloudByteOffsetRef = useRef<Record<string, number>>({});
  const reconnectAttemptRef = useRef<Record<string, number>>({});
  const reconnectTimerRef = useRef<Record<string, number>>({});
  const disposedTerminalIdsRef = useRef<Set<string>>(new Set());
  const fitFrameRef = useRef<number | null>(null);
  const terminalBufferRef = useRef<Record<string, string>>({});
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const callbacksRef = useRef({
    onCreate,
    onRawInput,
    onResize,
    onCloudFrame,
  });

  const [terminalSearchQuery, setTerminalSearchQuery] = useState('');
  const [shellProfile, setShellProfile] = useState(() => {
    if (typeof window === 'undefined') return 'powershell';
    return window.localStorage.getItem('arceus.terminal.shell_profile') || 'powershell';
  });
  const [copyFlash, setCopyFlash] = useState(false);

  const isLocalTerminal = Boolean(activeTerminal?.id?.startsWith('local-'));
  const isLocalPtyTerminal = isLocalTerminal && (activeTerminal?.backend || 'node-pty') === 'node-pty';
  const isCloudTerminal = Boolean(activeTerminal?.id?.startsWith('cloud-') || activeTerminal?.id?.startsWith('pty-'));
  const isInteractiveTerminal = isLocalPtyTerminal || isCloudTerminal;

  const runtimeLabel = isLocalPtyTerminal
    ? 'Host terminal'
    : isCloudTerminal
      ? 'Cloud PTY'
      : activeTerminal?.backend
        ? activeTerminal.backend
        : 'Command runner';
  const runtimeHint = isLocalPtyTerminal
    ? 'Local PowerShell runs on this computer inside the trusted folder. It has normal host network access; Docker sandbox isolation is used by agent runtime/check commands, not this local terminal.'
    : isCloudTerminal
      ? 'Cloud PTY streams through the Agent API and is bound to this workspace session.'
      : 'Command runner uses the backend workspace runtime when no local PTY is available.';
  const outputMatches = terminalSearchQuery
    ? output.toLowerCase().split(terminalSearchQuery.toLowerCase()).length - 1
    : 0;

  const sendCloudFrame = (terminalId: string, frame: Record<string, any>) => {
    const payload = JSON.stringify(frame);
    const socket = terminalsRef.current[terminalId]?.socket;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(payload);
      return;
    }
    if (socket?.readyState === WebSocket.CONNECTING) {
      pendingCloudFramesRef.current.push(payload);
    }
  };

  const appendTerminalBuffer = (terminalId: string, value: string) => {
    if (!terminalId || !value) return;
    terminalBufferRef.current[terminalId] = `${terminalBufferRef.current[terminalId] || ''}${value}`.slice(-250000);
  };

  const changeShellProfile = (value: string) => {
    setShellProfile(value);
    if (typeof window !== 'undefined') window.localStorage.setItem('arceus.terminal.shell_profile', value);
  };

  useEffect(() => {
    callbacksRef.current = {
      onCreate,
      onRawInput,
      onResize,
      onCloudFrame,
    };
  }, [onCloudFrame, onCreate, onRawInput, onResize]);

  // Handle auto-scroll on active output changes
  useEffect(() => {
    const viewport = viewportRef.current;
    if (viewport) viewport.scrollTop = viewport.scrollHeight;
  }, [activeTerminal?.id, output]);

  // Clean up cache when terminals are deleted/removed from sessions list
  useEffect(() => {
    const sessionIds = new Set(sessions.map((s) => s.id));
    Object.keys(terminalsRef.current).forEach((id) => {
      if (!sessionIds.has(id)) {
        const cache = terminalsRef.current[id];
        disposedTerminalIdsRef.current.add(id);
        if (reconnectTimerRef.current[id]) {
          window.clearTimeout(reconnectTimerRef.current[id]);
          delete reconnectTimerRef.current[id];
        }
        cache.socket?.close(1000, 'terminal removed');
        cache.terminal.dispose();
        delete terminalsRef.current[id];
        delete terminalBufferRef.current[id];
        delete cloudByteOffsetRef.current[id];
        delete reconnectAttemptRef.current[id];
      }
    });
  }, [sessions]);

  // Global Resize Observer on the viewport parent container
  useEffect(() => {
    if (!open || !viewportRef.current) return;

    const fitAll = () => {
      Object.keys(terminalsRef.current).forEach((id) => {
        try {
          terminalsRef.current[id].fitAddon.fit();
        } catch (e) {}
      });
    };

    const resizeObserver = new ResizeObserver(() => {
      if (fitFrameRef.current !== null) {
        window.cancelAnimationFrame(fitFrameRef.current);
      }
      fitFrameRef.current = window.requestAnimationFrame(() => {
        fitFrameRef.current = null;
        fitAll();
      });
    });
    resizeObserver.observe(viewportRef.current);

    return () => {
      resizeObserver.disconnect();
      if (fitFrameRef.current !== null) {
        window.cancelAnimationFrame(fitFrameRef.current);
        fitFrameRef.current = null;
      }
    };
  }, [open]);

  // Handle local PTY logs updates
  useEffect(() => {
    if (!activeTerminal?.id || !isLocalPtyTerminal) return;
    const cache = terminalsRef.current[activeTerminal.id];
    if (!cache) return;
    if (!rawOutput) return;

    const buffered = terminalBufferRef.current[activeTerminal.id] || '';
    if (rawOutput === buffered) {
      cache.lastRawOutputLength = rawOutput.length;
      return;
    }

    if (rawOutput.startsWith(buffered)) {
      const chunk = rawOutput.slice(buffered.length);
      if (chunk) {
        cache.terminal.write(chunk);
        appendTerminalBuffer(activeTerminal.id, chunk);
      }
      cache.lastRawOutputLength = rawOutput.length;
      return;
    }

    const previousLength = cache.lastRawOutputLength;
    if (rawOutput.length >= previousLength) {
      const chunk = rawOutput.slice(previousLength);
      if (chunk) {
        cache.terminal.write(chunk);
        appendTerminalBuffer(activeTerminal.id, chunk);
      }
    } else {
      cache.terminal.clear();
      if (rawOutput) cache.terminal.write(rawOutput);
      terminalBufferRef.current[activeTerminal.id] = rawOutput;
    }
    cache.lastRawOutputLength = rawOutput.length;
  }, [activeTerminal?.id, isLocalPtyTerminal, rawOutput]);

  // Handle interactive search query execution
  useEffect(() => {
    if (!terminalSearchQuery || !isInteractiveTerminal || !activeTerminal?.id) return;
    const cache = terminalsRef.current[activeTerminal?.id];
    if (cache) {
      cache.searchAddon.findNext(terminalSearchQuery);
    }
  }, [activeTerminal?.id, isInteractiveTerminal, terminalSearchQuery]);

  // Kill backend cloud PTY on tab kill
  useEffect(() => {
    if (!isCloudTerminal || activeTerminal?.status !== 'killed' || !activeTerminal?.id) return;
    sendCloudFrame(activeTerminal.id, { type: 'kill' });
    const cache = terminalsRef.current[activeTerminal.id];
    if (cache) {
      cache.socket?.close();
      cache.socket = null;
    }
  }, [activeTerminal?.id, activeTerminal?.status, isCloudTerminal]);

  // Dynamic initializer called by React ref callback per terminal container
  const initializeTerminalInstance = (id: string, el: HTMLDivElement, isCloud: boolean) => {
    disposedTerminalIdsRef.current.delete(id);
    if (terminalsRef.current[id]) {
      if (id === activeTerminal?.id) {
        terminalsRef.current[id].terminal.focus();
        try {
          terminalsRef.current[id].fitAddon.fit();
        } catch (e) {}
      }
      return;
    }

    const terminal = new XtermTerminal({
      cursorBlink: true,
      convertEol: true,
      fontFamily: 'var(--font-mono), Consolas, monospace',
      fontSize: 11,
      lineHeight: 1.35,
      scrollback: 5000,
      theme: {
        background: '#0b0c0f',
        foreground: '#d7dbe4',
        cursor: '#8b5cf6',
        selectionBackground: '#30234d',
        black: '#0b0c0f',
        red: '#f87171',
        green: '#86efac',
        yellow: '#fbbf24',
        blue: '#93c5fd',
        magenta: '#c084fc',
        cyan: '#67e8f9',
        white: '#e5e7eb',
        brightBlack: '#71717a',
        brightRed: '#fca5a5',
        brightGreen: '#bbf7d0',
        brightYellow: '#fde68a',
        brightBlue: '#bfdbfe',
        brightMagenta: '#ddd6fe',
        brightCyan: '#a5f3fc',
        brightWhite: '#ffffff',
      },
    });

    const fitAddon = new FitAddon();
    const searchAddon = new SearchAddon();
    const webLinksAddon = new WebLinksAddon();

    terminal.loadAddon(fitAddon);
    terminal.loadAddon(searchAddon);
    terminal.loadAddon(webLinksAddon);

    terminal.open(el);

    const initialOutput = terminalBufferRef.current[id] || (sessions.find((s) => s.id === id) ? terminalOutput(sessions.find((s) => s.id === id)!) : '');
    if (initialOutput) {
      terminal.write(initialOutput);
      terminalBufferRef.current[id] = initialOutput.slice(-250000);
    }

    let socket: WebSocket | null = null;

    if (isCloud) {
      if (!sessionId) {
        terminal.writeln('Open or create a workspace session before starting cloud PTY.');
      } else {
        const connect = () => {
          const offset = cloudByteOffsetRef.current[id] || 0;
          const ws = new WebSocket(terminalWebSocketUrl(sessionId, id, shellProfile, offset));
          socket = ws;
          if (terminalsRef.current[id]) {
            terminalsRef.current[id].socket = ws;
          }

          ws.onopen = () => {
            reconnectAttemptRef.current[id] = 0;
            const pending = pendingCloudFramesRef.current.splice(0);
            pending.forEach((payload) => ws.send(payload));
            callbacksRef.current.onCloudFrame?.(id, { type: 'connecting', status: 'connecting' });
          };

          ws.onmessage = (event) => {
            try {
              const frame = JSON.parse(event.data);
              const frameType = frame.type || frame.event;
              callbacksRef.current.onCloudFrame?.(id, frame);

              if (typeof frame.byte_offset === 'number') {
                if (frame.byte_offset <= (cloudByteOffsetRef.current[id] || 0)) return;
                cloudByteOffsetRef.current[id] = frame.byte_offset;
              }

              if (frameType === 'output' && frame.data) {
                const text = String(frame.data);
                terminal.write(text);
                appendTerminalBuffer(id, text);
              }
              if (frameType === 'ready' && !offset) {
                terminal.writeln(`\r\nPTY ready: ${frame.cwd || 'workspace'}\r\n`);
              }
              if (frameType === 'blocked') {
                terminal.writeln(`\r\nBlocked: ${frame.reason || 'command was denied'}\r\n`);
              }
              if (frameType === 'error') {
                terminal.writeln(`\r\nError: ${frame.message || 'terminal failed'}\r\n`);
              }
              if (frameType === 'exit') {
                terminal.writeln(`\r\nTerminal exited${frame.reason ? ` (${frame.reason})` : ''}.\r\n`);
              }
            } catch {
              const text = String(event.data);
              terminal.write(text);
              appendTerminalBuffer(id, text);
            }
          };

          const scheduleReconnect = () => {
            if (disposedTerminalIdsRef.current.has(id)) return;
            const currentSession = sessions.find((s) => s.id === id);
            if (['killed', 'exited', 'failed'].includes(currentSession?.status || '')) return;
            const attempt = (reconnectAttemptRef.current[id] || 0) + 1;
            reconnectAttemptRef.current[id] = attempt;
            const delay = Math.min(2 ** attempt * 500, 10000);
            terminal.writeln(`\r\n[Reconnecting in ${Math.ceil(delay / 1000)}s...]\r\n`);
            if (reconnectTimerRef.current[id]) {
              window.clearTimeout(reconnectTimerRef.current[id]);
            }
            reconnectTimerRef.current[id] = window.setTimeout(() => {
              delete reconnectTimerRef.current[id];
              connect();
            }, delay);
          };

          ws.onerror = () => {
            callbacksRef.current.onCloudFrame?.(id, { type: 'error', message: 'Terminal WebSocket failed.' });
          };

          ws.onclose = (event) => {
            callbacksRef.current.onCloudFrame?.(id, { type: 'exit' });
            if (event.code !== 1000) scheduleReconnect();
          };
        };
        connect();
      }
    }

    terminal.onData((data) => {
      if (isCloud) {
        sendCloudFrame(id, { type: 'input', data });
      } else {
        callbacksRef.current.onRawInput?.(id, data);
      }
    });

    terminal.onResize(({ cols, rows }) => {
      const cache = terminalsRef.current[id];
      if (cache?.lastResize?.cols === cols && cache.lastResize.rows === rows) return;
      if (cache) cache.lastResize = { cols, rows };
      if (isCloud) {
        sendCloudFrame(id, { type: 'resize', cols, rows });
      } else {
        callbacksRef.current.onResize?.(id, cols, rows);
      }
    });

    terminal.onKey(({ domEvent }) => {
      if (domEvent.ctrlKey && domEvent.key.toLowerCase() === 't') {
        domEvent.preventDefault();
        callbacksRef.current.onCreate(shellProfile);
      }
      if (domEvent.ctrlKey && domEvent.key.toLowerCase() === 'f') {
        domEvent.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
      }
      if (domEvent.ctrlKey && domEvent.key.toLowerCase() === 'l') {
        domEvent.preventDefault();
        if (isCloud) {
          sendCloudFrame(id, { type: 'input', data: '\x0c' });
        } else {
          callbacksRef.current.onRawInput?.(id, '\x0c');
        }
        terminal.clear();
      }
      if (domEvent.key === 'Escape') {
        setTerminalSearchQuery('');
        terminal.focus();
      }
    });

    terminalsRef.current[id] = {
      terminal,
      fitAddon,
      searchAddon,
      socket,
      lastRawOutputLength: initialOutput.length,
    };

    setTimeout(() => {
      try {
        fitAddon.fit();
      } catch (e) {}
      if (id === activeTerminal?.id) {
        terminal.focus();
      }
    }, 120);
  };

  const copyOutput = async () => {
    const activeId = activeTerminal?.id;
    const activeCache = activeId ? terminalsRef.current[activeId] : null;
    const selected = (isInteractiveTerminal && activeCache) ? activeCache.terminal.getSelection() : '';
    const value = selected || output;
    if (!value) return;
    await navigator.clipboard?.writeText(value);
    setCopyFlash(true);
    window.setTimeout(() => setCopyFlash(false), 700);
  };

  if (!open) return null;

  return (
    <section className={`${styles.terminalPanel} ${styles[`terminalPanel${size[0].toUpperCase()}${size.slice(1)}`]}`} aria-label="Workspace terminal">
      <header className={styles.terminalHeader}>
        <div className={styles.terminalTabs}>
          {sessions.map((terminal, index) => (
            <button
              key={terminal.id}
              type="button"
              className={terminal.id === activeTerminal?.id ? styles.terminalTabActive : styles.terminalTab}
              title={terminal.cwd || terminal.id}
              onClick={() => onSelect(terminal.id)}
            >
              <Terminal size={12} />
              <span>Terminal {index + 1}</span>
              <em data-status={terminal.status}>{terminal.status || 'active'}</em>
            </button>
          ))}
          <button className={styles.terminalIconButton} type="button" onClick={() => onCreate(shellProfile)} disabled={!canUseTerminal || busy} title="New terminal">
            <Plus size={13} />
          </button>
        </div>
        <div className={styles.terminalHeaderActions}>
          <span className={styles.terminalStatus} data-status={status}>{status}</span>
          <select
            className={styles.terminalShellSelect}
            value={shellProfile}
            onChange={(event) => changeShellProfile(event.target.value)}
            title="Shell profile for cloud PTY terminals"
          >
            <option value="powershell">PowerShell</option>
            <option value="pwsh">PowerShell 7</option>
            <option value="cmd">cmd</option>
            <option value="bash">Bash</option>
            <option value="zsh">Zsh</option>
            <option value="sh">sh</option>
          </select>
          <label className={styles.terminalSearch} title="Search terminal output">
            <Search size={12} />
            <input
              ref={searchInputRef}
              type="search"
              value={terminalSearchQuery}
              onChange={(event) => setTerminalSearchQuery(event.target.value)}
              placeholder="Search"
            />
            <em>{outputMatches || ''}</em>
          </label>
          <button type="button" className={copyFlash ? styles.copyFlash : undefined} onClick={copyOutput} disabled={!output} title={copyFlash ? 'Copied' : 'Copy terminal output'}><Copy size={13} /></button>
          <button type="button" onClick={() => activeTerminal && onClear(activeTerminal.id)} disabled={!activeTerminal} title="Clear terminal"><Trash2 size={13} /></button>
          <button type="button" onClick={() => activeTerminal && onRestart(activeTerminal.id)} disabled={!activeTerminal || busy} title="Restart terminal"><RotateCcw size={13} /></button>
          <button type="button" onClick={() => activeTerminal && onKill(activeTerminal.id)} disabled={!activeTerminal || status === 'killed'} title="Kill terminal"><Square size={12} /></button>
          {size !== 'compact' && <button type="button" onClick={() => onSizeChange('compact')} title="Compact terminal"><ChevronsDown size={13} /></button>}
          {size === 'compact' && <button type="button" onClick={() => onSizeChange('half')} title="Expand terminal"><ChevronsUp size={13} /></button>}
          {size !== 'max' ? (
            <button type="button" onClick={() => onSizeChange('max')} title="Maximize terminal"><Maximize2 size={13} /></button>
          ) : (
            <button type="button" onClick={() => onSizeChange('half')} title="Restore terminal"><Minimize2 size={13} /></button>
          )}
          <button type="button" onClick={onClose} title="Close terminal"><X size={13} /></button>
        </div>
      </header>

      <div className={styles.terminalCwd}>
        <span>cwd:</span>
        <strong title={activeTerminal?.cwd || helpText}>{activeTerminal?.cwd || helpText}</strong>
        <em
          className={isLocalPtyTerminal ? styles.terminalRuntimeLocal : isCloudTerminal ? styles.terminalRuntimeCloud : styles.terminalRuntimeFallback}
          title={runtimeHint}
        >
          {runtimeLabel}
        </em>
        {activeTerminal?.backend && activeTerminal.backend !== 'node-pty' && (
          <em title="Full interactive terminal requires node-pty. This session is using command-bar mode.">
            {activeTerminal.backend}
          </em>
        )}
      </div>

      <div className={styles.terminalViewport} ref={viewportRef}>
        {sessions.map((terminal) => {
          const isLocal = terminal.id.startsWith('local-');
          const isPty = isLocal && (terminal.backend || 'node-pty') === 'node-pty';
          const isCloud = terminal.id.startsWith('cloud-') || terminal.id.startsWith('pty-');
          const isInteractive = isPty || isCloud;
          const isActive = terminal.id === activeTerminal?.id;

          if (!isInteractive) {
            return isActive ? (
              <div key={terminal.id} style={{ height: '100%' }}>
                {output ? <pre>{output}</pre> : <p>Terminal ready. Run a command below.</p>}
              </div>
            ) : null;
          }

          return (
            <div
              key={terminal.id}
              style={{ display: isActive ? 'block' : 'none', height: '100%', width: '100%' }}
              ref={(el) => {
                if (el) {
                  initializeTerminalInstance(terminal.id, el, isCloud);
                }
              }}
            />
          );
        })}
        
        {sessions.length === 0 && (
          <div className={styles.terminalEmpty}>
            <Terminal size={16} />
            <span>{helpText}</span>
            <button type="button" onClick={() => onCreate(shellProfile)} disabled={!canUseTerminal || busy}>New terminal</button>
          </div>
        )}
      </div>

      {isInteractiveTerminal ? (
        <div className={styles.terminalHint}>
          {isLocalPtyTerminal
            ? 'Local host terminal: commands run in the selected folder and can use your normal Windows network. Use agent checks/runtime commands for Docker sandbox isolation.'
            : 'Type directly in the cloud PTY. Use local folder mode for host filesystem commands.'}
        </div>
      ) : (
        <form
          className={styles.terminalCommandBar}
          onSubmit={(event) => {
            event.preventDefault();
            onSend();
          }}
        >
          <span>&gt;</span>
          <input
            value={command}
            onChange={(event) => onCommandChange(event.target.value)}
            placeholder="Run a command in this workspace"
            disabled={!canUseTerminal || busy}
            autoComplete="off"
            spellCheck={false}
          />
          <button type="submit" disabled={!canUseTerminal || busy || !command.trim()}>Run</button>
        </form>
      )}
    </section>
  );
}
