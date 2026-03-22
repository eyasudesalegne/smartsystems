## Import and publish

1. Apply SQL in `sql/unified_production_schema_v2.sql` then the migrations in order.
2. Start PostgreSQL, Ollama, the FastAPI service, then n8n.
3. Import workflows using `n8n/manifest/import_order.txt`.
4. Attach credentials and activate only the two ingress workflows plus scheduler.
5. Use `/publish <post_id>` only after the corresponding social approval is `approved`.
