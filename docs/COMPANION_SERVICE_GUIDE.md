## Companion service

The service is a FastAPI application under `service/app`. It owns AI generation, embedding calls, retrieval, approvals, metrics, and command execution. `worker.py` is the durable queue worker entrypoint. The service uses the same Postgres schema as n8n and is safe to run separately from n8n.
