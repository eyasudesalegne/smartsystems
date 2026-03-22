## Data lifecycle management

This package now includes additive retention-policy and cleanup controls for operational tables that naturally grow over time.

### Covered resources
- `audit_logs`
- `connector_execution_log`
- `smoke_test_results`
- `queue_backend_events`
- `workflow_version_events`
- `ai_route_runs`
- `document_ingestion_runs`
- `dead_letter_items`

### Endpoints
- `POST /lifecycle/policy`
- `POST /lifecycle/report`
- `POST /lifecycle/run-cleanup`
- `GET /admin/lifecycle`

### Operational pattern
1. Run the lifecycle report first.
2. Review `eligible_total` and per-resource policy settings.
3. Run cleanup with `dry_run=true`.
4. Move to `dry_run=false` only after the report is acceptable.
5. Keep DLQ archiving enabled where incident forensics matter.

### Notes
- DLQ rows are archived into `dlq_archives` before delete when `archive_before_delete=true`.
- Cleanup is batch-based and additive; it does not change existing queue, connector, release, or workflow behavior.
- This is not a full enterprise ILM platform, but it provides a real operational baseline for retention and cleanup.
