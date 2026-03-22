import time
import httpx
from .config import settings


class OllamaError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class OllamaClient:
    def __init__(self):
        self.base = settings.ollama_base_url.rstrip('/')
        self.timeout = httpx.Timeout(90.0, connect=5.0)

    def tags(self):
        try:
            r = httpx.get(f'{self.base}/api/tags', timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            raise OllamaError('AI_UNAVAILABLE', f'Ollama unreachable: {e}')

    def generate(self, prompt: str, system_prompt: str | None = None, format_schema: dict | None = None, model: str | None = None):
        selected_model = (model or settings.ollama_model).strip()
        payload = {'model': selected_model, 'prompt': prompt, 'stream': False}
        if system_prompt:
            payload['system'] = system_prompt
        if format_schema:
            payload['format'] = format_schema
        t0 = time.time()
        try:
            r = httpx.post(f'{self.base}/api/generate', json=payload, timeout=self.timeout)
            if r.status_code == 404:
                raise OllamaError('MODEL_NOT_FOUND', f'Model not found: {selected_model}')
            r.raise_for_status()
            data = r.json()
            return data.get('response', ''), int((time.time() - t0) * 1000)
        except OllamaError:
            raise
        except Exception as e:
            raise OllamaError('AI_UNAVAILABLE', f'Ollama generate failed: {e}')

    def embed(self, input_text: str, model: str | None = None):
        selected_model = (model or settings.ollama_embedding_model).strip()
        payload = {'model': selected_model, 'input': input_text}
        try:
            r = httpx.post(f'{self.base}/api/embed', json=payload, timeout=self.timeout)
            if r.status_code == 404:
                raise OllamaError('MODEL_NOT_FOUND', f'Embedding model not found: {selected_model}')
            r.raise_for_status()
            data = r.json()
            embeds = data.get('embeddings') or []
            if not embeds:
                raise OllamaError('AI_UNAVAILABLE', 'Embedding response missing embeddings')
            return embeds[0]
        except OllamaError:
            raise
        except Exception as e:
            raise OllamaError('AI_UNAVAILABLE', f'Ollama embed failed: {e}')
