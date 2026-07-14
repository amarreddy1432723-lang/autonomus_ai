'use client';

import dynamic from 'next/dynamic';
import { Braces, Code2, Save, Wand2, X, Minimize2, Maximize2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import styles from './Workspace.module.css';
import ProblemsPanel from './ProblemsPanel';

const MonacoEditor = dynamic(() => import('@monaco-editor/react'), {
  ssr: false,
  loading: () => <div className={styles.editorLoading}>Loading editor...</div>,
});

const LSP_LANGUAGES = new Set(['typescript', 'javascript', 'python', 'css', 'json']);

export type OpenWorkspaceFile = {
  id: string;
  filename: string;
  content: string;
  dirty: boolean;
};

export type WorkspaceDiagnostic = {
  file?: string;
  line?: number;
  column?: number;
  severity?: 'error' | 'warning' | 'info' | string;
  message?: string;
  source?: string;
};

type Props = {
  file: OpenWorkspaceFile | null;
  tabs: OpenWorkspaceFile[];
  activeFileId: string;
  busy: boolean;
  onChange: (content: string) => void;
  onSave: () => void;
  onSelectTab: (fileId: string) => void;
  onCloseTab: (fileId: string) => void;
  onInlineEdit: (instruction: string, selectedText: string, start: number, end: number) => void;
  onComplete: (cursor: number) => void;
  onToggleExpand?: () => void;
  isCollapsed?: boolean;
  diagnostics?: WorkspaceDiagnostic[];
  onOpenDiagnostic?: (diagnostic: WorkspaceDiagnostic) => void;
  onDiagnosticsChange?: (diagnostics: WorkspaceDiagnostic[]) => void;
  workspaceRoot?: string;
};

function languageLabel(filename: string) {
  const extension = filename.split('.').pop()?.toLowerCase();
  if (!extension) return 'text';
  if (extension === 'tsx') return 'React TSX';
  if (extension === 'ts') return 'TypeScript';
  if (extension === 'js') return 'JavaScript';
  if (extension === 'py') return 'Python';
  if (extension === 'json') return 'JSON';
  if (extension === 'md') return 'Markdown';
  return extension.toUpperCase();
}

function monacoLanguage(filename: string) {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.tsx')) return 'typescript';
  if (lower.endsWith('.ts')) return 'typescript';
  if (lower.endsWith('.jsx')) return 'javascript';
  if (lower.endsWith('.js')) return 'javascript';
  if (lower.endsWith('.py')) return 'python';
  if (lower.endsWith('.json')) return 'json';
  if (lower.endsWith('.md')) return 'markdown';
  if (lower.endsWith('.css')) return 'css';
  if (lower.endsWith('.html')) return 'html';
  if (lower.endsWith('.yml') || lower.endsWith('.yaml')) return 'yaml';
  return 'plaintext';
}

function documentUri(filename: string, workspaceRoot?: string) {
  const normalizedFile = filename.replace(/\\/g, '/').replace(/^\/+/, '');
  const normalizedRoot = String(workspaceRoot || '').replace(/\\/g, '/').replace(/\/+$/, '');
  const absolute = normalizedRoot && !/^[A-Za-z]:\//.test(normalizedFile) && !normalizedFile.startsWith('/')
    ? `${normalizedRoot}/${normalizedFile}`
    : normalizedFile;
  const withSlash = /^[A-Za-z]:\//.test(absolute) ? `/${absolute}` : absolute.startsWith('/') ? absolute : `/${absolute}`;
  return `file://${withSlash.split('/').map((part, index) => index === 0 ? part : encodeURIComponent(part)).join('/')}`;
}

function lspWebSocketUrl(language: string, workspaceRoot?: string) {
  const rootParam = workspaceRoot ? `?root=${encodeURIComponent(workspaceRoot)}` : '';
  const agentUrl = process.env.NEXT_PUBLIC_AGENT_URL;
  if (agentUrl) {
    return `${agentUrl.replace(/^http/i, 'ws').replace(/\/$/, '')}/api/v1/code/lsp/${language}${rootParam}`;
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/api/v1/code/lsp/${language}${rootParam}`;
}

function configureMonacoWorkers() {
  if (typeof window === 'undefined') return;
  const monacoWindow = window as typeof window & {
    MonacoEnvironment?: {
      getWorker?: (_moduleId: string, label: string) => Worker;
    };
  };
  if (monacoWindow.MonacoEnvironment?.getWorker) return;
  monacoWindow.MonacoEnvironment = {
    ...(monacoWindow.MonacoEnvironment || {}),
    getWorker: (_moduleId: string, label: string) => {
      if (label === 'json') {
        return new Worker(new URL('monaco-editor/esm/vs/language/json/json.worker.js', import.meta.url), { type: 'module' });
      }
      if (label === 'css' || label === 'scss' || label === 'less') {
        return new Worker(new URL('monaco-editor/esm/vs/language/css/css.worker.js', import.meta.url), { type: 'module' });
      }
      if (label === 'html' || label === 'handlebars' || label === 'razor') {
        return new Worker(new URL('monaco-editor/esm/vs/language/html/html.worker.js', import.meta.url), { type: 'module' });
      }
      if (label === 'typescript' || label === 'javascript') {
        return new Worker(new URL('monaco-editor/esm/vs/language/typescript/ts.worker.js', import.meta.url), { type: 'module' });
      }
      return new Worker(new URL('monaco-editor/esm/vs/editor/editor.worker.js', import.meta.url), { type: 'module' });
    },
  };
}

function diagnosticMatchesFile(diagnostic: WorkspaceDiagnostic, filename?: string) {
  if (!filename) return false;
  const normalizedFile = filename.replace(/\\/g, '/').toLowerCase();
  const diagnosticFile = String(diagnostic.file || '').replace(/\\/g, '/').toLowerCase();
  if (!diagnosticFile || diagnosticFile === 'unknown') return true;
  return normalizedFile.endsWith(diagnosticFile) || diagnosticFile.endsWith(normalizedFile) || normalizedFile.endsWith(diagnosticFile.split('/').pop() || '');
}

function lspCompletionKind(monaco: any, kind?: number) {
  const map: Record<number, any> = {
    2: monaco.languages.CompletionItemKind.Method,
    3: monaco.languages.CompletionItemKind.Function,
    4: monaco.languages.CompletionItemKind.Constructor,
    5: monaco.languages.CompletionItemKind.Field,
    6: monaco.languages.CompletionItemKind.Variable,
    7: monaco.languages.CompletionItemKind.Class,
    8: monaco.languages.CompletionItemKind.Interface,
    9: monaco.languages.CompletionItemKind.Module,
    10: monaco.languages.CompletionItemKind.Property,
    12: monaco.languages.CompletionItemKind.Value,
    13: monaco.languages.CompletionItemKind.Enum,
    14: monaco.languages.CompletionItemKind.Keyword,
    15: monaco.languages.CompletionItemKind.Snippet,
    17: monaco.languages.CompletionItemKind.File,
    18: monaco.languages.CompletionItemKind.Reference,
  };
  return map[kind || 0] || monaco.languages.CompletionItemKind.Text;
}

function severityFromLsp(value?: number) {
  if (value === 2) return 'warning';
  if (value === 3 || value === 4) return 'info';
  return 'error';
}

function filenameFromUri(uri?: string) {
  if (!uri) return 'unknown';
  try {
    return decodeURIComponent(uri.replace(/^file:\/\/\/?/, '')).replace(/\//g, '\\');
  } catch {
    return uri;
  }
}

function isGeneratedOrLargeFile(file?: OpenWorkspaceFile | null) {
  if (!file) return false;
  const normalized = file.filename.replace(/\\/g, '/').toLowerCase();
  return /(^|\/)(node_modules|\.git|__pycache__|pycache|\.next|dist|build|coverage)(\/|$)/.test(normalized)
    || /\.(pyc|pyo|map|min\.js)$/.test(normalized)
    || file.content.length > 1_000_000;
}

export default function EditorPanel({ file, tabs, activeFileId, busy, onChange, onSave, onSelectTab, onCloseTab, onInlineEdit, onComplete, onToggleExpand, isCollapsed, diagnostics = [], onOpenDiagnostic, onDiagnosticsChange, workspaceRoot }: Props) {
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);
  const providerDisposablesRef = useRef<any[]>([]);
  const lspSocketRef = useRef<WebSocket | null>(null);
  const lspLanguageRef = useRef('');
  const lspInitializedRef = useRef(false);
  const lspRequestIdRef = useRef(1);
  const lspDocumentVersionRef = useRef(1);
  const lspPendingRef = useRef<Map<number, { resolve: (value: any) => void; reject: (reason?: any) => void }>>(new Map());
  const lspOpenedDocumentRef = useRef('');
  const [editInstruction, setEditInstruction] = useState('');
  const [lineTarget, setLineTarget] = useState('');
  const [lspDiagnostics, setLspDiagnostics] = useState<WorkspaceDiagnostic[]>([]);
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });

  const combinedDiagnostics = useMemo(() => {
    const seen = new Set<string>();
    return [...lspDiagnostics, ...diagnostics].filter((item) => {
      const key = `${item.file || ''}:${item.line || 0}:${item.column || 0}:${item.message || ''}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [diagnostics, lspDiagnostics]);

  const closeLsp = useCallback(() => {
    lspPendingRef.current.forEach((pending) => pending.reject(new Error('LSP connection closed.')));
    lspPendingRef.current.clear();
    lspSocketRef.current?.close();
    lspSocketRef.current = null;
    lspLanguageRef.current = '';
    lspInitializedRef.current = false;
    lspOpenedDocumentRef.current = '';
    setLspDiagnostics([]);
    onDiagnosticsChange?.([]);
  }, [onDiagnosticsChange]);

  const sendLspPayload = useCallback((payload: any) => {
    const socket = lspSocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(payload));
    return true;
  }, []);

  const ensureLsp = useCallback(async (language: string) => {
    if (typeof window === 'undefined' || !LSP_LANGUAGES.has(language)) return false;
    const current = lspSocketRef.current;
    if (current?.readyState === WebSocket.OPEN && lspLanguageRef.current === language) return true;
    closeLsp();
    await new Promise<void>((resolve, reject) => {
      const socket = new WebSocket(lspWebSocketUrl(language, workspaceRoot));
      const timeout = window.setTimeout(() => {
        socket.close();
        reject(new Error('LSP connection timed out.'));
      }, 2500);
      socket.onopen = () => {
        window.clearTimeout(timeout);
        lspSocketRef.current = socket;
        lspLanguageRef.current = language;
        resolve();
      };
      socket.onerror = () => {
        window.clearTimeout(timeout);
        reject(new Error('LSP unavailable.'));
      };
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (typeof message.id === 'number' && lspPendingRef.current.has(message.id)) {
            const pending = lspPendingRef.current.get(message.id);
            lspPendingRef.current.delete(message.id);
            if (message.error) pending?.reject(message.error);
            else pending?.resolve(message.result);
          } else if (message.method === 'textDocument/publishDiagnostics') {
            const fileName = filenameFromUri(message.params?.uri);
            const incoming = (message.params?.diagnostics || []).map((item: any) => ({
              file: fileName,
              line: Number(item.range?.start?.line || 0) + 1,
              column: Number(item.range?.start?.character || 0) + 1,
              severity: severityFromLsp(item.severity),
              message: item.message || 'Language server diagnostic',
              source: item.source || 'LSP',
            }));
            setLspDiagnostics((current) => {
              const next = [
                ...current.filter((item) => item.file !== fileName),
                ...incoming,
              ];
              onDiagnosticsChange?.(next);
              return next;
            });
          }
        } catch {
          // LSP logs are non-blocking for editor UX.
        }
      };
      socket.onclose = closeLsp;
    });
    if (!lspInitializedRef.current) {
      const id = lspRequestIdRef.current++;
      sendLspPayload({
        jsonrpc: '2.0',
        id,
        method: 'initialize',
        params: {
          processId: null,
          rootUri: workspaceRoot ? documentUri('', workspaceRoot) : null,
          workspaceFolders: workspaceRoot ? [{ uri: documentUri('', workspaceRoot), name: workspaceRoot.replace(/\\/g, '/').split('/').filter(Boolean).pop() || 'workspace' }] : null,
          capabilities: {
            textDocument: {
              completion: { completionItem: { snippetSupport: true } },
              hover: { contentFormat: ['markdown', 'plaintext'] },
              definition: {},
              references: {},
              rename: {},
            },
          },
        },
      });
      sendLspPayload({ jsonrpc: '2.0', method: 'initialized', params: {} });
      lspInitializedRef.current = true;
    }
    return true;
  }, [closeLsp, onDiagnosticsChange, sendLspPayload, workspaceRoot]);

  const requestLsp = useCallback(async (method: string, params: any) => {
    if (!file) return null;
    const language = monacoLanguage(file.filename);
    const available = await ensureLsp(language).catch(() => false);
    if (!available) return null;
    const uri = documentUri(file.filename, workspaceRoot);
    if (lspOpenedDocumentRef.current !== uri) {
      sendLspPayload({
        jsonrpc: '2.0',
        method: 'textDocument/didOpen',
        params: {
          textDocument: {
            uri,
            languageId: language,
            version: 1,
            text: file.content,
          },
        },
      });
      lspOpenedDocumentRef.current = uri;
      lspDocumentVersionRef.current = 1;
    }
    const id = lspRequestIdRef.current++;
    return new Promise<any>((resolve, reject) => {
      lspPendingRef.current.set(id, { resolve, reject });
      sendLspPayload({ jsonrpc: '2.0', id, method, params });
      window.setTimeout(() => {
        if (lspPendingRef.current.has(id)) {
          lspPendingRef.current.delete(id);
          resolve(null);
        }
      }, 2200);
    });
  }, [ensureLsp, file, sendLspPayload, workspaceRoot]);

  const configureMonaco = useCallback((monaco: any) => {
    configureMonacoWorkers();
    monaco.languages.typescript.typescriptDefaults.setDiagnosticsOptions({
      noSemanticValidation: false,
      noSyntaxValidation: false,
    });
    monaco.languages.typescript.javascriptDefaults.setDiagnosticsOptions({
      noSemanticValidation: false,
      noSyntaxValidation: false,
    });
    const compilerOptions = {
      target: monaco.languages.typescript.ScriptTarget.ES2020,
      allowNonTsExtensions: true,
      moduleResolution: monaco.languages.typescript.ModuleResolutionKind.NodeJs,
      module: monaco.languages.typescript.ModuleKind.ESNext,
      jsx: monaco.languages.typescript.JsxEmit.ReactJSX,
      allowJs: true,
      checkJs: true,
    };
    monaco.languages.typescript.typescriptDefaults.setCompilerOptions(compilerOptions);
    monaco.languages.typescript.javascriptDefaults.setCompilerOptions(compilerOptions);
    monaco.languages.json?.jsonDefaults?.setDiagnosticsOptions?.({
      validate: true,
      allowComments: true,
      schemas: [],
      enableSchemaRequest: true,
    });
    monaco.languages.css?.cssDefaults?.setOptions?.({ validate: true });
    monaco.languages.css?.scssDefaults?.setOptions?.({ validate: true });
    monaco.languages.css?.lessDefaults?.setOptions?.({ validate: true });
  }, []);

  const registerProviders = useCallback((monaco: any) => {
    providerDisposablesRef.current.forEach((disposable) => disposable.dispose?.());
    providerDisposablesRef.current = ['typescript', 'javascript', 'python', 'css', 'json'].flatMap((language) => [
      monaco.languages.registerCompletionItemProvider(language, {
        triggerCharacters: ['.', '/', '@'],
        provideCompletionItems: async (model: any, position: any) => {
          const result = await requestLsp('textDocument/completion', {
            textDocument: { uri: String(model.uri) },
            position: { line: position.lineNumber - 1, character: position.column - 1 },
          }).catch(() => null);
          const items = Array.isArray(result) ? result : result?.items || [];
          return {
            suggestions: items.slice(0, 60).map((item: any) => ({
              label: item.label,
              kind: lspCompletionKind(monaco, item.kind),
              insertText: item.insertText || item.label,
              detail: item.detail,
              documentation: item.documentation?.value || item.documentation,
              range: undefined,
            })),
          };
        },
      }),
      monaco.languages.registerHoverProvider(language, {
        provideHover: async (model: any, position: any) => {
          const result = await requestLsp('textDocument/hover', {
            textDocument: { uri: String(model.uri) },
            position: { line: position.lineNumber - 1, character: position.column - 1 },
          }).catch(() => null);
          const contents = result?.contents;
          if (!contents) return null;
          const value = Array.isArray(contents)
            ? contents.map((item: any) => item.value || item).join('\n\n')
            : contents.value || contents;
          return { contents: [{ value: String(value) }] };
        },
      }),
      monaco.languages.registerDefinitionProvider(language, {
        provideDefinition: async (model: any, position: any) => {
          const result = await requestLsp('textDocument/definition', {
            textDocument: { uri: String(model.uri) },
            position: { line: position.lineNumber - 1, character: position.column - 1 },
          }).catch(() => null);
          const target = Array.isArray(result) ? result[0] : result;
          if (!target?.uri || !target.range) return null;
          return {
            uri: monaco.Uri.parse(target.uri),
            range: new monaco.Range(target.range.start.line + 1, target.range.start.character + 1, target.range.end.line + 1, target.range.end.character + 1),
          };
        },
      }),
      monaco.languages.registerReferenceProvider(language, {
        provideReferences: async (model: any, position: any) => {
          const result = await requestLsp('textDocument/references', {
            textDocument: { uri: String(model.uri) },
            position: { line: position.lineNumber - 1, character: position.column - 1 },
            context: { includeDeclaration: true },
          }).catch(() => null);
          return (Array.isArray(result) ? result : []).map((item: any) => ({
            uri: monaco.Uri.parse(item.uri),
            range: new monaco.Range(item.range.start.line + 1, item.range.start.character + 1, item.range.end.line + 1, item.range.end.character + 1),
          }));
        },
      }),
      monaco.languages.registerRenameProvider(language, {
        provideRenameEdits: async (model: any, position: any, newName: string) => {
          const result = await requestLsp('textDocument/rename', {
            textDocument: { uri: String(model.uri) },
            position: { line: position.lineNumber - 1, character: position.column - 1 },
            newName,
          }).catch(() => null);
          const changes = result?.changes || {};
          const edits = Object.entries(changes).flatMap(([uri, textEdits]: [string, any]) =>
            (Array.isArray(textEdits) ? textEdits : []).map((edit: any) => ({
              resource: monaco.Uri.parse(uri),
              edit: {
                range: new monaco.Range(edit.range.start.line + 1, edit.range.start.character + 1, edit.range.end.line + 1, edit.range.end.character + 1),
                text: edit.newText,
              },
            })),
          );
          return { edits };
        },
      }),
    ]);
  }, [requestLsp]);

  useEffect(() => {
    configureMonacoWorkers();
  }, []);

  useEffect(() => {
    if (!file) return;
    const language = monacoLanguage(file.filename);
    if (!LSP_LANGUAGES.has(language)) return;
    let cancelled = false;
    ensureLsp(language).then((available) => {
      if (!available || cancelled) return;
      const uri = documentUri(file.filename, workspaceRoot);
      const previousUri = lspOpenedDocumentRef.current;
      if (previousUri && previousUri !== uri) {
        sendLspPayload({
          jsonrpc: '2.0',
          method: 'textDocument/didClose',
          params: { textDocument: { uri: previousUri } },
        });
        setLspDiagnostics((current) => {
          const previousFile = filenameFromUri(previousUri);
          const next = current.filter((item) => item.file !== previousFile);
          onDiagnosticsChange?.(next);
          return next;
        });
      }
      if (lspOpenedDocumentRef.current === uri) return;
      sendLspPayload({
        jsonrpc: '2.0',
        method: 'textDocument/didOpen',
        params: {
          textDocument: {
            uri,
            languageId: language,
            version: 1,
            text: file.content,
          },
        },
      });
      lspOpenedDocumentRef.current = uri;
      lspDocumentVersionRef.current = 1;
    }).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [ensureLsp, file?.id, file?.filename, onDiagnosticsChange, sendLspPayload, workspaceRoot]);

  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    const model = editor?.getModel?.();
    if (!editor || !monaco || !model || !file) return;
    const normalizedFile = file.filename.replace(/\\/g, '/').toLowerCase();
    const markers = combinedDiagnostics
      .filter((item) => {
        const diagnosticFile = String(item.file || '').replace(/\\/g, '/').toLowerCase();
        if (!diagnosticFile || diagnosticFile === 'unknown') return true;
        return normalizedFile.endsWith(diagnosticFile) || diagnosticFile.endsWith(normalizedFile) || normalizedFile.endsWith(diagnosticFile.split('/').pop() || '');
      })
      .map((item) => {
        const severity = String(item.severity || 'error').toLowerCase();
        return {
          startLineNumber: Math.max(1, Number(item.line || 1)),
          startColumn: Math.max(1, Number(item.column || 1)),
          endLineNumber: Math.max(1, Number(item.line || 1)),
          endColumn: Math.max(2, Number(item.column || 1) + 1),
          message: item.message || 'Workspace diagnostic',
          source: item.source || 'Arceus checks',
          severity: severity.includes('warn')
            ? monaco.MarkerSeverity.Warning
            : severity.includes('info')
              ? monaco.MarkerSeverity.Info
              : monaco.MarkerSeverity.Error,
        };
      });
    monaco.editor.setModelMarkers(model, 'Arceus-diagnostics', markers);
  }, [combinedDiagnostics, file]);

  const handleEditorChange = (value?: string) => {
    const nextValue = value || '';
    onChange(nextValue);
    if (!file || !lspOpenedDocumentRef.current) return;
    lspDocumentVersionRef.current += 1;
    sendLspPayload({
      jsonrpc: '2.0',
      method: 'textDocument/didChange',
      params: {
        textDocument: {
          uri: documentUri(file.filename, workspaceRoot),
          version: lspDocumentVersionRef.current,
        },
        contentChanges: [{ text: nextValue }],
      },
    });
  };

  useEffect(() => () => {
    providerDisposablesRef.current.forEach((disposable) => disposable.dispose?.());
    closeLsp();
  }, [closeLsp]);

  const runInlineEdit = () => {
    const editor = editorRef.current;
    const model = editor?.getModel?.();
    if (!editor || !model || !file) return;
    const selection = editor.getSelection();
    const start = model.getOffsetAt(selection.getStartPosition());
    const end = model.getOffsetAt(selection.getEndPosition());
    const selectedText = file.content.slice(start, end);
    onInlineEdit(editInstruction, selectedText, start, end);
  };

  const runCompletion = () => {
    const editor = editorRef.current;
    const model = editor?.getModel?.();
    if (!editor || !model || !file) return;
    onComplete(model.getOffsetAt(editor.getPosition()));
  };

  const goToLine = () => {
    const editor = editorRef.current;
    const line = Number.parseInt(lineTarget, 10);
    if (!editor || !Number.isFinite(line) || line < 1) return;
    editor.revealLineInCenter(line);
    editor.setPosition({ lineNumber: line, column: 1 });
    editor.focus();
  };

  const openDiagnostic = (diagnostic: WorkspaceDiagnostic) => {
    if (!file || !diagnosticMatchesFile(diagnostic, file.filename)) {
      onOpenDiagnostic?.(diagnostic);
      return;
    }
    const editor = editorRef.current;
    const line = Math.max(1, Number(diagnostic.line || 1));
    const column = Math.max(1, Number(diagnostic.column || 1));
    editor?.revealPositionInCenter({ lineNumber: line, column });
    editor?.setPosition({ lineNumber: line, column });
    editor?.focus();
  };

  const formatDocument = async () => {
    const editor = editorRef.current;
    if (!editor) return;
    await editor.getAction('editor.action.formatDocument')?.run();
  };

  const errorCount = combinedDiagnostics.filter((item) => String(item.severity || 'error').toLowerCase().includes('error')).length;
  const warningCount = combinedDiagnostics.filter((item) => String(item.severity || '').toLowerCase().includes('warn')).length;
  const activeReadOnly = isGeneratedOrLargeFile(file);

  return (
    <section className={styles.editor}>
      <div className={styles.panelHeader}>
        <span className={styles.editorTitle}><Code2 size={15} /> {file ? file.filename : 'Editor'}</span>
        {file && <span className={styles.meta}>{languageLabel(file.filename)}{file.dirty ? ' - unsaved' : ''}</span>}
        {onToggleExpand && (
          <button
            className={styles.editorCollapseButton}
            type="button"
            onClick={onToggleExpand}
            title={isCollapsed ? 'Expand Editor' : 'Close Editor'}
          >
            {isCollapsed ? <Maximize2 size={14} /> : <Minimize2 size={14} />}
          </button>
        )}
      </div>
      {tabs.length > 0 && (
        <div className={styles.editorTabs}>
          {tabs.map((tab) => (
            <div
              key={tab.id}
              className={tab.id === activeFileId ? styles.editorTabActive : styles.editorTab}
              title={tab.filename}
            >
              <button type="button" onClick={() => onSelectTab(tab.id)}>
                {isGeneratedOrLargeFile(tab) && <em>[Read-only]</em>}
                <span>{tab.filename}</span>
              </button>
              {tab.dirty && <strong aria-label="Unsaved changes" />}
              <button
                type="button"
                onClick={() => onCloseTab(tab.id)}
                aria-label={`Close ${tab.filename}`}
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
      {file ? (
        <>
          <div className={styles.editorToolbar}>
            <button className={styles.editorToolButton} type="button" onClick={formatDocument} disabled={busy}>
              <Braces size={14} /> Format
            </button>
            <div className={styles.goToLine}>
              <input
                value={lineTarget}
                onChange={(event) => setLineTarget(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') goToLine();
                }}
                inputMode="numeric"
                placeholder="Line"
              />
              <button type="button" onClick={goToLine}>Go</button>
            </div>
          </div>
          <div className={styles.monacoShell}>
            <MonacoEditor
              path={file.filename}
              language={monacoLanguage(file.filename)}
              theme="vs-dark"
              value={file.content}
              beforeMount={configureMonaco}
              onMount={(editor, monaco) => {
                monacoRef.current = monaco;
                editorRef.current = editor;
                registerProviders(monaco);
                const position = editor.getPosition?.();
                if (position) {
                  setCursorPosition({ line: position.lineNumber, column: position.column });
                }
                editor.onDidChangeCursorPosition((event: any) => {
                  setCursorPosition({ line: event.position.lineNumber, column: event.position.column });
                });
                editor.focus();
              }}
              onChange={handleEditorChange}
              options={{
                automaticLayout: true,
                fontFamily: 'var(--font-mono), Consolas, monospace',
                fontSize: 13,
                lineHeight: 21,
                minimap: { enabled: true },
                scrollBeyondLastLine: false,
                smoothScrolling: true,
                tabSize: 2,
                wordWrap: 'off',
                renderWhitespace: 'selection',
                bracketPairColorization: { enabled: true },
                guides: { bracketPairs: true, indentation: true },
                padding: { top: 12, bottom: 12 },
                readOnly: activeReadOnly,
                readOnlyMessage: { value: 'Generated or large files are opened read-only.' },
              }}
            />
          </div>
          <ProblemsPanel
            diagnostics={combinedDiagnostics}
            activeFile={file.filename}
            onOpenDiagnostic={openDiagnostic}
          />
          <div className={styles.inlineEditBar}>
            <input
              className={styles.inlineEditInput}
              value={editInstruction}
              onChange={(event) => setEditInstruction(event.target.value)}
              placeholder="Select code, then ask Arceus to edit it..."
            />
            <button className={styles.fullWidthButton} type="button" onClick={runInlineEdit} disabled={busy || !editInstruction.trim()}>
              <Wand2 size={14} /> AI Edit
            </button>
            <button className={styles.fullWidthButton} type="button" onClick={runCompletion} disabled={busy}>
              Complete
            </button>
          </div>
          <div className={styles.editorFooter}>
            <span className={styles.meta}>
              Ln {cursorPosition.line}, Col {cursorPosition.column}
              {' · '}{languageLabel(file.filename)}
              {' · '}{file.content.split('\n').length} lines
              {combinedDiagnostics.length ? ` · ${errorCount} errors / ${warningCount} warnings` : ' · clean'}
            </span>
            <button className={styles.sendButton} type="button" onClick={onSave} disabled={busy || !file.dirty}>
              <Save size={16} /> Save
            </button>
          </div>
        </>
      ) : (
        <div className={styles.emptyState}>
          <div>
            <h1>Open a file</h1>
            <p>Select a workspace file to inspect and edit it before asking Arceus to plan or patch.</p>
          </div>
        </div>
      )}
    </section>
  );
}
