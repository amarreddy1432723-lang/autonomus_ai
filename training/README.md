# Autonomus AI Training Workspace

This workspace prepares Autonomus AI as a fine-tuned open-weight model served through an OpenAI-compatible endpoint.

## Target

- Model name: `autonomus-ai-v1`
- Default base model: `Qwen/Qwen3-8B`
- Fine-tuning method: LoRA/QLoRA
- Serving layer: vLLM OpenAI-compatible server

## Workflow

1. Curate opt-in examples into `data/raw_examples.jsonl`.
2. Run `python scripts/prepare_dataset.py` to clean and write `data/train.jsonl`.
3. Fine-tune with your preferred LoRA/QLoRA trainer using `data/train.jsonl`.
4. Export or merge the adapter as `autonomus-ai-v1`.
5. Serve it with vLLM at `/v1/chat/completions`.
6. Set backend env:

```bash
LLM_PROVIDER=autonomus
LLM_MODEL=autonomus-ai-v1
AUTONOMUS_LLM_BASE_URL=http://localhost:8000/v1
AUTONOMUS_LLM_API_KEY=not-needed
```

## Data Rules

Use only approved examples. Do not train on secrets, API keys, private memory, passwords, or low-quality failed conversations.

Each JSONL row should follow `schema/autonomus_instruction.schema.json`.

## Composer-Style Chat Approvals

The chat UI can capture opt-in examples when a user clicks **Train Autonomus** on a strong assistant response. Those candidates are written to `data/candidate_examples.jsonl` with a `quality_status`.

Export only approved examples:

```bash
python scripts/export_approved_examples.py
```

The export writes `data/approved_from_chat.jsonl`. Rejected examples, errors, and unapproved private chat history are not included.
