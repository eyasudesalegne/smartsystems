## Retrieval and embeddings

Phase 3 keeps the Phase 2 hybrid retrieval design: try pgvector if available, otherwise use lexical/full-text fallback. Ingested notes and paper chunks are persisted, searched, and their source references are included in AI artifacts. Publication bundle summaries also record grounding references.


## Governed document ingestion
- Use `POST /rag/documents/ingest` to persist governed source material into `documents` and `document_chunks`.
- When the embedding model is available, the service records per-chunk version metadata in `embedding_versions` so retrieval changes can be audited later.
- `GET /rag/governance` and `scripts/build_rag_governance_report.py` summarize the governed document corpus for operators.

## AI routing interplay
- `POST /ai/route` selects a model + prompt pair for action types such as `fallback_chat`, `summarize`, and `retrieve_answer`.
- `POST /ai/generate` now uses the routed prompt template as the baseline system prompt and falls back across models when configured.
