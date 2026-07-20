export {};

declare global {
  type DesktopIpcResponse<T> = {
    requestId: string;
    ok: boolean;
    result?: T;
    error?: {
      code: string;
      message: string;
      retryable: boolean;
      details?: Record<string, unknown>;
    };
  };

  type DesktopWorkspace = {
    id: string;
    name: string;
    rootPath: string;
    repositoryType: 'git' | 'none';
    trusted: boolean;
    openedAt: string;
    lastOpenedAt: string;
    settingsPath: string;
  };

  type DesktopTerminalSession = {
    id: string;
    status: string;
    cwd: string;
    shell?: string;
    title?: string;
    createdBy?: 'user' | 'agent' | 'system';
    missionId?: string | null;
    agentId?: string | null;
    history: string[];
    logs: Array<Record<string, unknown>>;
    backend: string;
    created_at: string;
    updated_at: string;
  };

  interface Window {
    electron?: {
      isDesktop?: boolean;
      openExternal?: (url: string) => Promise<{ ok: boolean; message?: string }>;
      onAuthCode?: (callback: (data: { code?: string }) => void) => () => void;
    };
    arceusDesktop?: {
      isDesktop: boolean;
      capabilities: () => Promise<DesktopIpcResponse<Record<string, unknown>>>;
      diagnostics: () => Promise<DesktopIpcResponse<Record<string, unknown>>>;
      workspace: {
        openDirectory: (options?: { rootPath?: string; trusted?: boolean }) => Promise<DesktopIpcResponse<DesktopWorkspace | null>>;
        setTrust: (rootPath: string, trusted: boolean) => Promise<DesktopIpcResponse<DesktopWorkspace>>;
        readDirectoryTree: (rootPath: string) => Promise<{ root: string; items: Array<Record<string, unknown>>; count: number }>;
        discoverTasks: (rootPath: string) => Promise<DesktopIpcResponse<{ rootPath: string; tasks: Array<Record<string, unknown>> }>>;
      };
      filesystem: {
        readFile: (rootPath: string, relativePath: string) => Promise<DesktopIpcResponse<{ path: string; content: string; size_bytes: number }>>;
        writeFile: (rootPath: string, relativePath: string, content: string) => Promise<DesktopIpcResponse<{ path: string; size_bytes: number; atomic: boolean }>>;
      };
      terminal: {
        create: (rootPath: string, options?: Record<string, unknown>) => Promise<DesktopIpcResponse<DesktopTerminalSession>>;
        sendInput: (terminalId: string, input: string, options?: Record<string, unknown>) => Promise<DesktopIpcResponse<DesktopTerminalSession | { id: string; ignored: boolean }>>;
        resize: (terminalId: string, cols: number, rows: number) => Promise<{ id: string; resized: boolean }>;
        kill: (terminalId: string) => Promise<DesktopIpcResponse<DesktopTerminalSession | { id: string; status: string }>>;
        onData: (callback: (data: { id: string; seq: number; data: string; timestamp: string }) => void) => () => void;
        onExit: (callback: (data: { id: string; code: number | null; signal?: string | null; timestamp: string }) => void) => () => void;
      };
      updater: {
        install: () => Promise<{ ok: boolean; message?: string }>;
        onAvailable: (callback: (data: Record<string, unknown>) => void) => () => void;
        onReady: (callback: (data: Record<string, unknown>) => void) => () => void;
        onStatus: (callback: (data: Record<string, unknown>) => void) => () => void;
      };
      system: {
        minimize: () => void;
        maximize: () => void;
        close: () => void;
        openExternal: (url: string) => Promise<{ ok: boolean; message?: string }>;
        openRoute: (route: string) => void;
        onAuthCode: (callback: (data: { code?: string }) => void) => () => void;
      };
    };
  }
}
