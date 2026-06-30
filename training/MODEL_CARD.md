# Autonomus AI v1 Model Card

## Intended Use

Autonomus AI v1 is planned as a personal learning and goal-execution assistant for this application. It should explain topics clearly, use goal context, support anatomy teaching, and avoid malformed tool-call text.

## Base Model

Default base: `Qwen/Qwen3-8B`

## Fine-Tuning Method

Start with LoRA/QLoRA supervised fine-tuning on curated instruction examples.

## Data Policy

Only opt-in, reviewed examples are trainable. Exclude secrets, API keys, passwords, private memory, and low-quality failed conversations.

## Serving Contract

The trained or adapter-served model must expose an OpenAI-compatible chat completions API:

- Base URL: `AUTONOMUS_LLM_BASE_URL`
- Model: `autonomus-ai-v1`
- Endpoint: `/v1/chat/completions`

## Promotion Gate

Promote a candidate model only after it passes:

- Anatomy explanation quality
- Goal-context alignment
- Media response quality
- Tool-call safety
- Refusal and error handling
- Latency and cost checks
