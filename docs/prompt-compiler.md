# Prompt Compiler & Cognitive Planning Engine

Part 37 adds a provider-neutral prompt compiler for Arceus runtime tasks.

## What It Produces

- Prompt Intermediate Representation (PIR)
- role instruction block
- cognitive execution plan
- authority-ranked prompt blocks
- policy and verification blocks
- delimited untrusted context blocks
- tool definitions
- output contract
- provider-adapted prompt for OpenAI, Anthropic, Gemini, Groq, or local models

## APIs

- `POST /api/v1/prompts/compile`
- `POST /api/v1/prompts/validate`
- `POST /api/v1/prompts/adapt`
- `GET /api/v1/prompts/templates`
- `GET /api/v1/prompts/cache`
- `DELETE /api/v1/prompts/cache`

## Safety Rules

- Platform and organization policies are mandatory.
- Lower-authority repository/context content is never treated as instructions.
- Prompt injection patterns in untrusted context are sanitized.
- Prompt injection in mandatory authoritative blocks blocks compilation.
- Output contracts are mandatory.
- Token budgeting excludes optional low-priority context before mandatory blocks.
