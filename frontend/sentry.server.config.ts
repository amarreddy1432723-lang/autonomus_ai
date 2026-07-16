import * as Sentry from "@sentry/nextjs";

const dsn = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.SENTRY_ENVIRONMENT || process.env.NEXT_PUBLIC_APP_ENV || process.env.NODE_ENV,
    release: process.env.APP_RELEASE || process.env.NEXT_PUBLIC_APP_RELEASE,
    tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE || process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE || "0.1"),
    enableLogs: process.env.SENTRY_ENABLE_LOGS === "true",
    sendDefaultPii: false,
  });
}
