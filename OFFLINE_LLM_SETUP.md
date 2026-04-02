# Offline LLM Setup

Lumen Vault now supports a configurable backend order for AI generation.

Default order:

```env
AI_BACKEND_ORDER=ollama,openai,llama_cpp
```

This means:

1. Try local `Ollama`
2. If not available, try `OpenAI`
3. If not available, try local `llama.cpp`

## Best local offline setup

Install Ollama on your PC and pull a small model:

```powershell
ollama pull qwen2.5:3b
```

Optional environment variables:

```env
OLLAMA_URL=http://127.0.0.1:11434/api/generate
OLLAMA_MODEL=qwen2.5:3b
AI_BACKEND_ORDER=ollama,openai,llama_cpp
```

If `OLLAMA_MODEL` is not set, Lumen Vault will try to detect a local Ollama model automatically.

## Run locally

1. Start Ollama
2. Run the app:

```bat
run_lumen_vault.bat
```

## Force offline-only mode

If you want to avoid cloud APIs completely on your own machine:

```env
AI_BACKEND_ORDER=ollama,llama_cpp
```

## Force OpenAI first

For hosted deployments:

```env
AI_BACKEND_ORDER=openai,ollama,llama_cpp
```

## Health check

Open:

```text
/lumen_vault/api/health
```

It now reports:

- current backend label
- configured backend order

