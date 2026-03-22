# Architecture

## 1. System overview

SmartSystems is a hybrid orchestration platform that combines **n8n** for workflow automation with a **FastAPI companion service** for deterministic execution, policy enforcement, retrieval, connector APIs, tenant-aware administration, and reporting.

At a high level, the system is composed of four layers:

1. **Ingress and orchestration layer**
   - n8n workflows receive requests from Telegram and web/webhook entry points.
   - n8n handles routing, scheduling, delivery notifications, workflow chaining, and operational bridges.

2. **Application control layer**
   - The FastAPI service exposes operational APIs for commands, jobs, releases, connectors, lifecycle controls, AI routing, RAG governance, approvals, and tenant-aware admin views.
   - This layer is where business rules, validation, tenant scoping, and operational safety checks are enforced.

3. **Persistence and state layer**
   - PostgreSQL is the system of record for workflows, jobs, approvals, queue state, release state, tenant state, governance state, and audit trails.

4. **AI and integration layer**
   - Ollama provides local generation and embedding support.
   - Connector specs and related workflows bridge the system to external services such as MLflow, Figma, Azure ML, PubMed, arXiv, Google Drive, and others.

## 2. Request flow

A typical request follows this path:

1. A request enters through Telegram or a webhook/web UI flow in n8n.
2. n8n normalizes the payload and forwards it to the FastAPI service.
3. The FastAPI service resolves tenant context, validates the request, applies policy checks, and determines whether the action is:
   - deterministic and directly executable,
   - queue-backed,
   - AI-assisted,
   - approval-gated, or
   - release-related.
4. The service reads/writes durable state in PostgreSQL.
5. If background execution is required, the request is placed onto the queue.
6. Workers claim queue items, execute the work, record attempts, and emit audit state.
7. n8n or the service returns results, notifications, or follow-up actions.

## 3. Major subsystems

## 3.1 n8n orchestration

The `n8n/import/` directory contains importable workflows for:
- ingress
- queue scheduling and worker coordination
- AI routing support
- connector catalog, preparation, smoke testing, and workflow-draft generation
- release engineering
- governance and tenant audits
- lifecycle and runtime reporting

## 3.2 FastAPI companion service

The `service/app/` package provides:
- API endpoints
- auth and secret handling
- database access
- connector execution surfaces
- retrieval and RAG operations
- lifecycle management
- tenant context and row isolation utilities
- worker logic

This service is the authoritative control plane for policy-heavy and stateful operations.

## 3.3 Queue and worker model

The queue subsystem persists work in database tables and tracks:
- queue items
- queue attempts
- job runs
- dead-letter items
- worker heartbeats

This design gives the system durable retries, auditable failures, and better operational visibility than an in-memory queue.

## 3.4 AI routing and RAG

AI-assisted flows are backed by Ollama for:
- text generation
- embeddings
- grounded retrieval workflows

RAG governance controls track ingestion, chunking, and embedding visibility so the system can report what knowledge is present and how it is being used.

## 3.5 Release engineering

Release workflows and service endpoints support:
- manifest creation
- checksum validation
- preflight checks
- publication tracking
- rollback bundle creation
- release channel planning and execution

## 3.6 Multi-tenancy and governance

Tenant-aware access is a core architectural concern. The platform includes:
- tenant resolution
- tenant membership
- tenant policy handling
- row-isolation controls
- tenant-scoped reporting
- query-scope and query-coverage audits

High-risk read paths are explicitly hardened to respect effective tenant context.

## 3.7 Connector platform

Connector support is defined through JSON specs plus service/workflow handling. Integrations span API-style and bridge-style patterns.

The architecture deliberately distinguishes among:
- **live API integrations**
- **partial integrations**
- **manual or bridge integrations**

This distinction is important for truthful productization and deployment planning.

## 4. Repository structure

- `connectors/specs/`: connector contracts and definitions
- `deploy/`: local deployment assets
- `docs/`: operational and architecture documentation
- `migrations/`: incremental schema evolution
- `n8n/import/`: workflows to import into n8n
- `n8n/manifest/`: workflow maps and import order
- `scripts/`: report generators, validation, and smoke utilities
- `service/`: FastAPI control-plane implementation
- `sql/`: base schema artifacts

## 5. Operational posture

This repository is best understood as a **source package for a production-oriented control plane**, not as a finished one-click SaaS product.

What is already real:
- importable workflows
- service code
- migrations
- connector registry/specs
- smoke tests and validators
- release and governance controls

What still depends on deployment context:
- live credentials
- external service connectivity
- real database-backed verification in the target environment
- environment-specific secrets, URLs, and policies

## 6. Publishing notes

For GitHub publication, generated bundles and transient runtime artifacts should remain out of the repository unless they are intentionally versioned release assets. The source of truth should stay focused on code, workflows, migrations, documentation, and scripts.
