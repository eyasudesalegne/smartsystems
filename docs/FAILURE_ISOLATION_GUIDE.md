# Failure Isolation Guide

This package now includes additive failure-isolation controls for connector execution and workflow execution caps.

## Connector runtime controls

Each connector can resolve an effective runtime policy from `connector_runtime_policies` or built-in defaults:

- `requests_per_window`
- `window_seconds`
- `timeout_seconds`
- `failure_threshold`
- `cooldown_seconds`

Runtime enforcement occurs before `POST /connectors/execute-live` dispatches the adapter call.

- If the recent execution volume exceeds the configured window budget, the endpoint returns `RATE_LIMITED`.
- If the connector circuit is open and still cooling down, the endpoint returns `CIRCUIT_OPEN`.
- If the downstream call times out, the timeout is recorded and contributes to circuit state.

## Workflow execution caps

Use `POST /workflows/execution/check` as a guard before running high-impact workflows. The endpoint can optionally persist the execution reservation into `audit_logs`.

## Reports

- `POST /connectors/failure-isolation-report`
- `scripts/build_connector_failure_isolation_report.py`
- `scripts/check_workflow_execution_caps.py`
- `n8n/import/wf_connector_failure_isolation_audit.json`
- `n8n/import/wf_workflow_execution_cap_guard.json`

## Tables

Migration `011_failure_isolation_controls.sql` adds:

- `connector_runtime_policies`
- `workflow_runtime_policies`
- additive runtime/isolation columns on `connector_metrics`
