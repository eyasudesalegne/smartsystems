# SmartSystems

SmartSystems is a production-oriented **AI workflow control plane** built around **n8n**, a **FastAPI companion service**, **PostgreSQL**, and **Ollama**.

It is designed to orchestrate AI-assisted workflows, governed retrieval pipelines, connector-driven integrations, approvals, release automation, and tenant-aware operations from a single backend package.

## What this repository contains

- **n8n workflows** for ingress, routing, orchestration, reporting, releases, governance, and connector operations
- **FastAPI service code** for execution, policy enforcement, retrieval, connector APIs, lifecycle controls, and tenant-aware admin endpoints
- **SQL schema and migrations** for queueing, approvals, release engineering, AI routing, lifecycle, and multi-tenancy
- **connector specifications** for supported external systems
- **validation, report-generation, and smoke-test scripts**
- **deployment scaffolding** for local or server-hosted setup

## Core capabilities

### AI orchestration
- AI task routing and execution through Ollama
- model and prompt-control support
- embeddings generation and grounded AI flows
- AI control and governance reporting

### RAG and document governance
- governed document ingestion
- notes and paper ingestion
- chunking and embedding flows
- retrieval endpoints and governance summaries

### Queueing and job control
- durable queue processing
- retries and dead-letter handling
- worker heartbeat and runtime auditing
- job status and cancellation flows

### Release engineering
- release manifest generation
- checksum validation
- preflight validation
- rollback package generation
- staged publication and channel execution

### Governance and approvals
- approval evaluation and transitions
- publication and social approval flows
- tenant policies and row-isolation controls
- enforcement, scope, and coverage reporting

### Connector platform
Includes connector support patterns for:
- MLflow
- Azure ML
- draw.io
- Figma
- Mermaid
- Canvas
- Kaggle
- NotebookLM
- Google Drive
- Overleaf
- PubMed
- arXiv
- Antigravity
- VS Code

Some connectors are implemented as live API-style flows, while others are intentionally bridge/manual patterns. The repository is explicit about that distinction and does not present bridge integrations as fully automated APIs.

## Repository layout

```text
smartsystems/
├── config/            # phase notes and configuration notes
├── connectors/        # connector specifications
├── deploy/            # docker-compose and environment examples
├── docs/              # architecture, guides, status, smoke-test docs
├── examples/          # example payloads and sample commands
├── migrations/        # incremental SQL migrations
├── n8n/               # importable workflows and manifests
├── prompts/           # codex/generation helper prompts
├── scripts/           # report builders, validators, smoke utilities
├── service/           # FastAPI companion service and tests
└── sql/               # base schema files
```

## Suggested publishing posture

This cleaned repository version is intended for GitHub publication:
- generated release artifacts were removed
- transient test cache files were removed
- documentation was consolidated around architecture and usage
- the repository is positioned as a source repository, not an artifact dump

## Quick start

1. Review `deploy/.env.example`
2. Start the stack with `deploy/docker-compose.yml`
3. Apply the SQL schema and migrations
4. Import workflows from `n8n/import/`
5. Configure required credentials and secrets
6. Run validation and smoke-test scripts

## Key docs

- `docs/ARCHITECTURE.md`
- `docs/API_REFERENCE.md`
- `docs/CONNECTORS_AND_SERVICE_INTEGRATIONS.md`
- `docs/MULTI_TENANCY_GUIDE.md`
- `docs/RELEASE_ENGINEERING_GUIDE.md`
- `docs/SMOKE_TEST_GUIDE.md`
- `docs/IMPLEMENTATION_STATUS_MATRIX.md`

## Notes

This repository is production-oriented, but some features still depend on the runtime environment you deploy it into. For example, real PostgreSQL verification, live external credentials, and certain enterprise connector modes require an actual deployment target and valid credentials.
