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

If Railway cannot provision Redis on the current plan, use Upstash Redis and apply it to backend services:

```powershell
$env:UPSTASH_REDIS_URL="rediss://default:<password>@<host>:6379"
.\scripts\setup-upstash-redis.ps1
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

## Runtime Telemetry APIs

Book II Part 45 adds first-class operational APIs:

- `POST /api/v1/telemetry/logs`
- `GET /api/v1/telemetry/logs`
- `POST /api/v1/telemetry/metrics`
- `GET /api/v1/telemetry/metrics`
- `POST /api/v1/telemetry/spans`
- `GET /api/v1/telemetry/traces/{trace_id}`
- `POST /api/v1/telemetry/provider-health`
- `POST /api/v1/telemetry/alerts`
- `GET /api/v1/telemetry/alerts`
- `POST /api/v1/telemetry/incidents`
- `POST /api/v1/telemetry/mission-statistics`
- `POST /api/v1/telemetry/cost-statistics`
- `GET /api/v1/telemetry/dashboard`
- `POST /api/v1/telemetry/exporters`
- `GET /api/v1/telemetry/exporters`
- `POST /api/v1/telemetry/alert-channels`
- `GET /api/v1/telemetry/alert-channels`
- `GET /api/v1/telemetry/alert-deliveries`
- `POST /api/v1/telemetry/alert-deliveries/{attempt_id}/send`
- `POST /api/v1/telemetry/alert-deliveries/drain`
- `POST /api/v1/telemetry/recovery-actions`
- `GET /api/v1/telemetry/recovery-actions`
- `POST /api/v1/telemetry/recovery-actions/{recovery_action_id}/execute`
- `GET /api/v1/telemetry/exporters/runtime-status`
- `GET /api/v1/telemetry/mission-control`

All persisted telemetry is tenant-scoped and correlated by trace ID, mission ID, workflow ID, service, and actor where available.

`POST /api/v1/telemetry/spans` persists spans to Postgres and also attempts to emit an OpenTelemetry SDK span when the SDK is installed and configured. Local development continues to work without OpenTelemetry installed.

## Persistence

Migration `k8f9a0b1c2d3_arceus_observability_aiops.py` creates:

- `arceus_telemetry_logs`
- `arceus_metric_samples`
- `arceus_traces`
- `arceus_spans`
- `arceus_alerts`
- `arceus_incidents`
- `arceus_provider_health`
- `arceus_mission_statistics`
- `arceus_cost_statistics`
- `arceus_dashboard_configs`

Migration `m0b1c2d3e4f5_arceus_observability_delivery_recovery.py` creates:

- `arceus_telemetry_exporter_configs`
- `arceus_alert_delivery_channels`
- `arceus_alert_delivery_attempts`
- `arceus_recovery_actions`

## Redaction

Telemetry ingestion redacts common secret patterns before persistence, including bearer tokens, `password=`, `token=`, `secret=`, and `sk-` values. Do not send raw prompts, source code, or personal data to telemetry unless explicitly permitted by policy.

## AIOps

The MVP AIOps layer provides:

- Provider health classification and reroute recommendations.
- Incident recommendations based on provider, queue, database, cost, and security signals.
- Operations dashboard recommendations based on active alerts, open incidents, degraded providers, total cost, and failed missions.
- Alert delivery configuration for Slack, email, Teams, and webhooks. Alerts create queued/suppressed delivery attempts based on channel filters.
- Exporter configuration records for Prometheus, Loki, Tempo, OTLP, and Sentry targets.
- Policy-gated recovery actions. Low-risk actions such as retrying failed checks or refreshing GitHub checks can auto-execute; high-risk actions require approval or are blocked when auto-execution is requested.
- Mission Control observability snapshots containing traces, logs, alerts, incidents, exporters, delivery channels, recovery actions, and AIOps recommendations.

Queued alert attempts can now be delivered by calling `POST /api/v1/telemetry/alert-deliveries/drain`.
Webhook, Slack, and Teams channels send JSON payloads to the configured URL. Email delivery uses SMTP when these environment variables are present:

```text
ARCEUS_SMTP_HOST=
ARCEUS_SMTP_PORT=587
ARCEUS_SMTP_USER=
ARCEUS_SMTP_PASSWORD=
ARCEUS_ALERT_FROM_EMAIL=
```

Vault-backed channel targets such as `vault://slack-webhook` intentionally fail with `secret_resolution_not_configured` until the production secret resolver worker is connected.

Low-risk recovery actions have safe executors for:

- `retry_failed_check`
- `restart_preview`
- `reroute_model_provider`
- `clear_context_cache`
- `refresh_github_checks`
- `requeue_worker_job`

High-risk actions remain blocked or approval-required by policy.

`GET /api/v1/telemetry/exporters/runtime-status` reports whether OpenTelemetry SDK/exporter envs are configured for live OTLP/Tempo/Loki-style export. Postgres span persistence continues even when external exporters are unavailable.

## Exporters And Channels

Recommended production mapping:

- Prometheus: metrics scrape and alert rules.
- Loki: structured application logs.
- Tempo: distributed traces.
- Slack or Teams: P0/P1 engineering alerts.
- Email: lower-priority release and billing alerts.
- Webhook: integration with external incident tooling.

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
