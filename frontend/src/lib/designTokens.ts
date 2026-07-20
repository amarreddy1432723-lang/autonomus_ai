export const tokens = {
  color: {
    background: {
      primary: 'var(--color-bg-primary)',
      secondary: 'var(--color-bg-secondary)',
      tertiary: 'var(--color-bg-tertiary)',
      elevated: 'var(--color-bg-elevated)',
      surface: 'var(--color-bg-surface)',
    },
    border: {
      default: 'var(--color-border)',
      focus: 'var(--color-border-focus)',
    },
    text: {
      primary: 'var(--color-text-primary)',
      secondary: 'var(--color-text-secondary)',
      muted: 'var(--color-text-tertiary)',
      code: 'var(--color-text-code)',
    },
    accent: {
      primary: 'var(--color-accent-primary)',
      secondary: 'var(--color-accent-secondary)',
    },
    semantic: {
      success: 'var(--color-success)',
      warning: 'var(--color-warning)',
      danger: 'var(--color-error)',
      info: 'var(--color-info)',
    },
  },
  typography: {
    display: 'var(--font-primary)',
    body: 'var(--font-primary)',
    code: 'var(--font-mono)',
  },
  spacing: {
    xs: 'var(--space-1)',
    sm: 'var(--space-2)',
    md: 'var(--space-3)',
    lg: 'var(--space-4)',
    xl: 'var(--space-6)',
    xxl: 'var(--space-8)',
  },
  radius: {
    sm: 'var(--radius-sm)',
    md: 'var(--radius-md)',
    lg: 'var(--radius-lg)',
    full: 'var(--radius-full)',
  },
  shadow: {
    sm: 'var(--shadow-sm)',
    md: 'var(--shadow-md)',
    glow: 'var(--shadow-glow)',
  },
  motion: {
    fast: '120ms',
    normal: '180ms',
    slow: '280ms',
    easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
  },
  opacity: {
    disabled: 0.45,
    muted: 0.68,
    overlay: 0.82,
  },
  zIndex: {
    base: 1,
    dropdown: 20,
    drawer: 40,
    modal: 60,
    toast: 80,
    commandPalette: 100,
  },
  breakpoints: {
    mobile: '480px',
    tablet: '768px',
    desktop: '1024px',
    wide: '1440px',
  },
  editor: {
    rowHeight: '26px',
    gutterWidth: '54px',
    tabHeight: '34px',
    terminalHeight: '260px',
  },
  status: {
    success: 'var(--color-success)',
    warning: 'var(--color-warning)',
    danger: 'var(--color-error)',
    info: 'var(--color-info)',
  },
} as const;

export type DesignTokens = typeof tokens;

