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
http://localhost:3001/d/arceus-code-overview
```

Automated verification:

```powershell
.\scripts\verify-observability.ps1
```

Runtime verification, after the stack is running:

```powershell
.\scripts\verify-observability.ps1 -CheckRuntime -Strict
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

Import the starter Grafana dashboard from:

```text
ops/grafana/arceus-code-overview.json
```

For the production-smoke stack, Grafana is auto-provisioned from:

- `ops/grafana/provisioning/datasources/prometheus.yml`
- `ops/grafana/provisioning/dashboards/arceus.yml`

## Logs

API services emit structured JSON logs with request ID, trace ID, route, duration, status, and safe user identifier.

## Alerts

Prometheus alert rules live in `ops/prometheus/arceus-alerts.yml`.

Required production alerts:

- `ArceusServiceDown`: service scrape failure for any Arceus API.
- `ArceusApiHighErrorRate`: error rate > 1 percent over 5 minutes.
- `ArceusApiP99LatencyHigh`: p99 latency > 3 seconds.
- `ArceusWorkerQueueDepthHigh`: job queue depth > 100.
- `ArceusWorkerDown`: worker count = 0.
- `ArceusDeadLetterJobs`: jobs entering dead-letter state.

Suggested routing:

- Critical service/worker down: PagerDuty.
- Error rate, latency, dead-letter growth: Slack.
- Disk usage > 80 percent: email or infrastructure alerting.

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
- required alert coverage
- Grafana dashboard artifact
- Grafana datasource/dashboard provisioning
- `scripts/verify-observability.ps1`
- observability runbook

For production, the Observability Gate should have zero warnings before a public release.

## Release Gate

The release gate runs the observability verifier before production approval:

```powershell
.\scripts\verify-release-gate.ps1 -Environment production -Phase predeploy -ReleaseVersion arceus-code-v1.0.0
```

For a real release, set these variables in CI or the deployment shell:

```text
SENTRY_DSN=
NEXT_PUBLIC_SENTRY_DSN=
APP_RELEASE=arceus-code-v1.0.0
NEXT_PUBLIC_APP_RELEASE=arceus-code-v1.0.0
PROMETHEUS_URL=http://localhost:9090
GRAFANA_URL=http://localhost:3001
```
