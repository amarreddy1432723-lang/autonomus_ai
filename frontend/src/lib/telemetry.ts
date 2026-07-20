type TelemetryProperties = Record<string, string | number | boolean | null | undefined>;

const BLOCKED_KEYS = ['password', 'secret', 'token', 'authorization', 'source', 'content', 'prompt', 'code'];

function sanitizeProperties(properties: TelemetryProperties = {}) {
  return Object.fromEntries(
    Object.entries(properties).filter(([key, value]) => {
      if (value === undefined) return false;
      return !BLOCKED_KEYS.some((blocked) => key.toLowerCase().includes(blocked));
    })
  );
}

export const telemetry = {
  event(name: string, properties: TelemetryProperties = {}) {
    if (process.env.NEXT_PUBLIC_TELEMETRY_DISABLED === 'true') return;
    const payload = {
      name,
      properties: sanitizeProperties(properties),
      route: typeof window !== 'undefined' ? window.location.pathname : undefined,
      release: process.env.NEXT_PUBLIC_APP_RELEASE || process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA,
      at: new Date().toISOString(),
    };
    if (process.env.NODE_ENV !== 'production') {
      console.info('[telemetry]', payload);
    }
  },
  error(name: string, error: unknown, properties: TelemetryProperties = {}) {
    const message = error instanceof Error ? error.message : String(error);
    this.event(name, { ...properties, errorMessage: message.slice(0, 240) });
  },
};

export const logger = {
  info(event: string, properties: TelemetryProperties = {}) {
    telemetry.event(event, properties);
  },
  warn(event: string, properties: TelemetryProperties = {}) {
    telemetry.event(event, { ...properties, severity: 'warning' });
  },
  error(event: string, error: unknown, properties: TelemetryProperties = {}) {
    telemetry.error(event, error, properties);
  },
};

