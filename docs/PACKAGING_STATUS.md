# PACKAGING STATUS

| snapshot | contains | state |
|---|---|---|
| v2_hybrid_n8n_ollama_control_plane_prod_connectors_upgraded.zip | base package from user | input |
| v3_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint1.zip | first upgraded checkpoint: spec-driven adapters, workflows, docs, migration 005, prompts | superseded checkpoint |
| v4_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint2.zip | deeper auth execution, connector persistence hooks, connector-only smoke path, expanded tests, refreshed handoff docs | superseded checkpoint |
| v5_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint3.zip | degraded health fallback, connector registry sync endpoint/workflow/script, migration 006 seed, persistence verification path, expanded tests/docs | superseded checkpoint |
| v6_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint4.zip | service-specific adapter wiring, normalized execute-live outputs, canonicalized env/template placeholders, updated workflow normalize nodes, expanded tests/docs | superseded checkpoint |

| v7_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint5.zip | standardized normalized/summary/pagination outputs for local/manual bridge connectors, richer artifact payloads for draw.io/Mermaid/Overleaf/VS Code/Antigravity, expanded local-connector tests and smoke assertions | superseded checkpoint |

| v8_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint6.zip | lazy DB pool initialization, connector preflight endpoint/script/workflow, preflight smoke scope, generated preflight report, expanded tests/docs | superseded checkpoint |

| v9_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint7.zip | workflow-manifest endpoint/script/workflow, generated workflow coverage report, manifest smoke scope, expanded tests/docs | superseded checkpoint |
| v10_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint8.zip | combined connector readiness-report endpoint/script/workflow, generated readiness report, readiness smoke scope, expanded tests/docs | superseded checkpoint |
| v11_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint9.zip | deployment-plan endpoint/script/workflow/report, deployment smoke scope, expanded tests/docs, refreshed handoff files | superseded checkpoint |

| v12_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint10.zip | rollout-bundle endpoint/script/workflow/generated report, rollout smoke scope, expanded tests/docs | superseded checkpoint |

- Latest local checkpoint prepared for packaging: v13_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint11.zip includes persistence-report endpoint/script/workflow/generated report, persistence-report smoke scope, import-order update, and expanded tests/docs.

- `v14_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint12.zip`: adds connector credential matrix endpoint/script/workflow/generated report plus smoke/validation coverage.

- `v15_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint13.zip`: adds enterprise auth/RBAC scaffolding, secrets service, request correlation/idempotency middleware baseline, Prometheus metrics mode, admin endpoints, connector health/metrics, migration 007, enterprise workflows, and expanded tests.

- `v16_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint14.zip`: adds workflow version history/rollback enforcement, migration 008 workflow version events, workflow-version smoke scope, new importable history/rollback workflows, and expanded enterprise tests/docs.

- `v17_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint15.zip`: adds pluggable queue backend abstraction (DB default + Redis optional fallback), worker concurrency/backoff/heartbeat enforcement, migration 009 queue runtime controls, queue runtime smoke coverage/report, and workflow `wf_queue_runtime_audit.json`.

- `v18_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint16.zip`: adds AI routing/prompt registry runtime, governed document ingestion + governance reporting, migration 010, AI/RAG smoke scopes, generated reports, and importable AI/RAG workflows.

- `v19_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint17.zip`: adds failure-isolation controls (migration 011, connector runtime policies, circuit/rate-limit/timeout enforcement, workflow execution-cap guards, isolation report scripts/workflows, new smoke scopes, and expanded tests/docs).

- `v20_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint18.zip`: adds release manifest/checksum/rollback/preflight endpoints, migration 012 release-engineering tables, release scripts/workflows/docs, generated release artifacts, and release smoke scopes.

- `v21_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint19.zip`: adds data-lifecycle controls (migration 013, retention policies, lifecycle report/cleanup endpoints, DLQ archival, scripts/workflows/docs, generated lifecycle reports, new smoke scopes, and expanded tests).

- `v22_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint20.zip`: adds tenant-hardening controls (migration 014, tenant context/admin endpoints, tenant report script, tenant workflows, generated tenant context report, smoke/validation coverage).
- `v23_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint21.zip`: adds stricter tenant route enforcement (migration 015, tenant route policies/access audit, enforcement report script/workflows/generated report, new smoke scope, and expanded tenant tests/docs).
- `v24_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint22.zip`: adds deeper release publication automation (migration 016, `/release/publish`, `/release/publications`, `/admin/releases`, publication report script, publication workflows, generated publication report, publication bundle artifact, and release-publication smoke coverage).

- `v25_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint23.zip`: adds stricter tenant row-isolation controls (migration 017, per-table row policies + row-access audit, middleware-backed route-to-table enforcement, row-isolation report script/workflows/generated report, new smoke scope, and expanded tenant tests/docs).

- `v26_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint24.zip`: adds deeper release publication-channel automation (migration 018, channel config/plan/admin endpoints, release channel report script/workflows/generated report, updated tenant row mapping, and release-channel smoke coverage).

- `v27_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint25.zip`: adds deeper release publication-channel execution automation (migration 019, channel execute/list/admin endpoints, release channel execution report script/workflows/generated report, updated tenant row mapping, and release-channel execution smoke coverage).

- v28_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint26.zip: adds migration 020 tenant query-scope controls, query-scope report/admin tooling, scoped release/publication list endpoints, new workflow/script/generated report, and validation coverage.
- v28_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint26.zip: adds migration 020 tenant query-scope controls, query-scope report/admin tooling, request-context scoped release/publication read paths, generated report/workflow/script, and validation coverage.

- v29_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint27.zip: adds tenant query coverage controls, expanded read-path scoping, new coverage report/script/workflow, migration 021, and updated docs/smoke validation.

- v30_hybrid_n8n_ollama_control_plane_prod_connectors_checkpoint28.zip: hardens direct tenant-scoped read endpoints, expands query-coverage targets to connector/job/RAG/lifecycle/tenant admin reads, and updates tests/docs/reporting for the new read-path slice.

