# Observability

## Error Tracking

Set `SENTRY_DSN` to enable backend Sentry capture and `NEXT_PUBLIC_SENTRY_DSN` to enable frontend capture. Suggested env:

```text
SENTRY_DSN=
NEXT_PUBLIC_SENTRY_DSN=
SENTRY_TRACES_SAMPLE_RATE=0.1
NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE=0.1
NEXT_PUBLIC_SENTRY_REPLAY_SAMPLE_RATE=0
NEXT_PUBLIC_SENTRY_REPLAY_ERROR_SAMPLE_RATE=0.1
SENTRY_PROFILES_SAMPLE_RATE=0
APP_ENV=production
NEXT_PUBLIC_APP_ENV=production
APP_RELEASE=<git-sha-or-version>
NEXT_PUBLIC_APP_RELEASE=<git-sha-or-version>
```

## Metrics

Prometheus metrics are exposed at:

```text
/metrics
```

Local production-smoke scrape test:

```powershell
docker compose -f docker-compose.prod-smoke.yml --profile observability up -d
```

Then open:

```text
http://localhost:9090/targets
```

Prometheus config lives in:

- `ops/prometheus/prometheus.yml`
- `ops/prometheus/arceus-alerts.yml`

Key dashboards:

- HTTP latency histogram
- API error rate
- Redis queue depth
- Celery worker count
- Docker container count
- job dead-letter growth

## Logs

API services emit structured JSON logs with request ID, trace ID, route, duration, status, and safe user identifier.

## Alerts

- Job queue depth > 100: PagerDuty
- Error rate > 1 percent over 5 minutes: Slack
- P99 latency > 3 seconds: Slack
- Celery worker count = 0: PagerDuty
- Disk usage > 80 percent: email

## Admin Gate

The Admin page calls:

```text
GET /api/v1/admin/observability-health
```

It checks:

- backend Sentry DSN
- frontend Sentry DSN
- Prometheus metrics exposure
- release tagging
- Prometheus config files
- alert rule files

For production, the Observability Gate should have zero warnings before a public release.
