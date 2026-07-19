export {};

declare global {
  interface Window {
    electron?: {
      isDesktop?: boolean;
      openExternal?: (url: string) => Promise<{ ok: boolean; message?: string }>;
      onAuthCode?: (callback: (data: { code?: string }) => void) => () => void;
    };
  }
}

