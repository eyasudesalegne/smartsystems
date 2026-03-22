#!/usr/bin/env bash
set -euo pipefail
APP_BASE_URL="${APP_BASE_URL:-http://localhost:8080}"
SMOKE_SCOPE="${SMOKE_SCOPE:-auto}"

run_live_core() {
  curl -sf "$APP_BASE_URL/health" >/dev/null
  curl -sf "$APP_BASE_URL/ready" >/dev/null || true
  curl -sf "$APP_BASE_URL/metrics" >/dev/null
  curl -sf -X POST "$APP_BASE_URL/ingest/note" -H "Content-Type: application/json" -d '{"tenant_id":"default","actor_id":"anonymous","title":"smoke","body":"retrieval smoke body"}' >/dev/null
  curl -sf -X POST "$APP_BASE_URL/retrieve/query" -H "Content-Type: application/json" -d '{"tenant_id":"default","query":"smoke"}' >/dev/null
  curl -sf "$APP_BASE_URL/connectors/catalog" >/dev/null
  curl -sf -X POST "$APP_BASE_URL/connectors/workflow-draft" -H "Content-Type: application/json" -d '{"service_name":"pubmed","operation_id":"search"}' >/dev/null
}

run_connector_only() {
  python scripts/smoke_test_connectors.py
}

run_persistence_checks() {
  python scripts/verify_connector_persistence.py
}

run_preflight_checks() {
  python scripts/connector_preflight_report.py --out docs/generated_connector_preflight_report.json
}

run_workflow_manifest_checks() {
  python scripts/build_connector_workflow_manifest.py --out docs/generated_connector_workflow_manifest.json
}

run_readiness_checks() {
  python scripts/build_connector_readiness_report.py --out docs/generated_connector_readiness_report.json
}

run_deployment_plan_checks() {
  python scripts/build_connector_deployment_plan.py --out docs/generated_connector_deployment_plan.json
}

run_rollout_bundle_checks() {
  python scripts/build_connector_rollout_bundle.py --out docs/generated_connector_rollout_bundle.json
}

run_persistence_report_checks() {
  python scripts/build_connector_persistence_report.py --out docs/generated_connector_persistence_report.json
}

run_credential_matrix_checks() {
  python scripts/build_connector_credential_matrix.py --out docs/generated_connector_credential_matrix.json
}

run_workflow_version_checks() {
  python scripts/check_workflow_versions.py
}

run_queue_runtime_checks() {
  python scripts/check_queue_runtime.py
}

run_ai_control_checks() {
  python scripts/build_ai_control_report.py --out docs/generated_ai_control_report.json
}

run_rag_governance_checks() {
  python scripts/build_rag_governance_report.py --out docs/generated_rag_governance_report.json
}


run_failure_isolation_checks() {
  python scripts/build_connector_failure_isolation_report.py --out docs/generated_connector_failure_isolation_report.json
}

run_workflow_execution_cap_checks() {
  python scripts/check_workflow_execution_caps.py --out docs/generated_workflow_execution_cap_report.json
}

run_release_manifest_checks() {
  python scripts/build_release_manifest.py --out docs/generated_release_manifest.json
}

run_release_checksum_checks() {
  python scripts/validate_release_checksums.py --out docs/generated_release_checksum_validation.json
}

run_release_rollback_checks() {
  python scripts/build_release_rollback_package.py --out docs/generated_release_rollback_package.json --out-zip artifacts/release_rollback_bundle_default.zip
}

run_release_preflight_checks() {
  python scripts/run_release_preflight.py --out docs/generated_release_preflight_report.json
}

run_release_publication_checks() {
  python scripts/build_release_publication_report.py --out docs/generated_release_publication_report.json --out-zip artifacts/release_publication_bundle_default.zip
}

run_release_channel_checks() {
  python scripts/build_release_channel_report.py --out docs/generated_release_channel_report.json
}

run_release_channel_execution_checks() {
  python scripts/build_release_channel_execution_report.py --out docs/generated_release_channel_execution_report.json
}

run_data_lifecycle_report_checks() {
  python scripts/build_data_lifecycle_report.py --out docs/generated_data_lifecycle_report.json
}

run_data_lifecycle_cleanup_checks() {
  python scripts/run_data_lifecycle_cleanup.py --dry-run --out docs/generated_data_lifecycle_cleanup.json
}

run_tenant_context_checks() {
  python scripts/build_tenant_context_report.py --out docs/generated_tenant_context_report.json
}


run_tenant_enforcement_checks() {
  python scripts/build_tenant_enforcement_report.py --out docs/generated_tenant_enforcement_report.json
}

run_tenant_row_isolation_checks() {
  python scripts/build_tenant_row_isolation_report.py --out docs/generated_tenant_row_isolation_report.json
}

run_tenant_query_scope_checks() {
  python scripts/build_tenant_query_scope_report.py --out docs/generated_tenant_query_scope_report.json
}

run_tenant_query_coverage_checks() {
  python scripts/build_tenant_query_coverage_report.py --out docs/generated_tenant_query_coverage_report.json
}

case "$SMOKE_SCOPE" in
  core)
    run_live_core
    ;;
  connectors)
    run_connector_only
    ;;
  persistence)
    run_persistence_checks
    ;;
  preflight)
    run_preflight_checks
    ;;
  manifest)
    run_workflow_manifest_checks
    ;;
  readiness)
    run_readiness_checks
    ;;
  deployment)
    run_deployment_plan_checks
    ;;
  rollout)
    run_rollout_bundle_checks
    ;;
  persistence_report)
    run_persistence_report_checks
    ;;
  credential_matrix)
    run_credential_matrix_checks
    ;;
  workflow_versions)
    run_workflow_version_checks
    ;;
  queue_runtime)
    run_queue_runtime_checks
    ;;
  ai_control)
    run_ai_control_checks
    ;;
  rag_governance)
    run_rag_governance_checks
    ;;
  failure_isolation)
    run_failure_isolation_checks
    ;;
  workflow_caps)
    run_workflow_execution_cap_checks
    ;;
  release_manifest)
    run_release_manifest_checks
    ;;
  release_checksums)
    run_release_checksum_checks
    ;;
  release_rollback)
    run_release_rollback_checks
    ;;
  release_preflight)
    run_release_preflight_checks
    ;;
  release_publication)
    run_release_publication_checks
    ;;
  release_channels)
    run_release_channel_checks
    ;;
  release_channel_execution)
    run_release_channel_execution_checks
    ;;
  lifecycle_report)
    run_data_lifecycle_report_checks
    ;;
  lifecycle_cleanup)
    run_data_lifecycle_cleanup_checks
    ;;
  tenant_context)
    run_tenant_context_checks
    ;;
  tenant_enforcement)
    run_tenant_enforcement_checks
    ;;
  tenant_row_isolation)
    run_tenant_row_isolation_checks
    ;;
  tenant_query_scope)
    run_tenant_query_scope_checks
    ;;
  tenant_query_coverage)
    run_tenant_query_coverage_checks
    ;;
  auto)
    if curl -sf "$APP_BASE_URL/health" >/dev/null 2>&1; then
      run_live_core
    else
      run_connector_only
    fi
    ;;
  *)
    echo "Unsupported SMOKE_SCOPE=$SMOKE_SCOPE" >&2
    exit 2
    ;;
esac
