# Arceus Model Gateway, Routing and Inference Infrastructure

Part 41 adds a provider-independent model gateway facade for choosing models across OpenAI, Anthropic, Gemini, Groq, local Ollama/vLLM, enterprise providers, and future adapters.

## API Surface

- `GET /api/v1/model-gateway/catalog`
- `POST /api/v1/model-gateway/route`
- `POST /api/v1/model-gateway/estimate`
- `POST /api/v1/model-gateway/infer`
- `GET /api/v1/model-gateway/health`
- `POST /api/v1/model-gateway/feedback`

## Current Capabilities

- Unified request schema for model routing and dry-run inference.
- Capability, modality, context window, structured output, streaming, tool calling, deterministic, region, retention, cost, and latency filtering.
- Weighted routing modes: balanced, quality-first, latency-first, cost-first, privacy-first.
- Cost estimation with prompt caching awareness.
- Provider health and circuit-breaker readiness summaries.
- Fallback model selection.
- Quality feedback loop that updates model task scores.
- Optional persistence of routing decisions and dry-run execution ledger records when a mission id is provided.

## Production Next Steps

- Connect `/infer` to live provider adapters behind explicit environment/provider configuration.
- Add streaming token events.
- Add retry/fallback execution across selected candidates.
- Add structured output validation from Prompt Compiler contracts.
- Add budget reservations before live inference.
- Add Sentry/Prometheus metrics for latency, cost, error rate, fallback usage, and provider health.
