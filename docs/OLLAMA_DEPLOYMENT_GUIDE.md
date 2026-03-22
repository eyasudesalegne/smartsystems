## Ollama deployment

Pull the required local models before starting the service:
- `ollama pull gemma3`
- `ollama pull embeddinggemma`

If Ollama is unavailable, the service returns `AI_UNAVAILABLE` or `MODEL_NOT_FOUND` without faking outputs.
