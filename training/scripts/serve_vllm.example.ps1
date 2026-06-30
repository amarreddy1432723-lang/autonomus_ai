$env:MODEL="autonomus-ai-v1"
$env:BASE_MODEL="Qwen/Qwen3-8B"

python -m vllm.entrypoints.openai.api_server `
  --model $env:BASE_MODEL `
  --served-model-name $env:MODEL `
  --host 0.0.0.0 `
  --port 8000
