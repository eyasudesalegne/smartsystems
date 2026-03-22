
from typing import Any, Literal
from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: Literal['ok', 'degraded']
    postgres: str
    ollama: str
    model: str | None = None
    embedding_model: str | None = None
    queue_depth: int | None = None

class GenerateRequest(BaseModel):
    tenant_id: str = 'default'
    actor_id: str = 'anonymous'
    request_id: str | None = None
    prompt: str
    system_prompt: str | None = None
    action_type: str = 'fallback_chat'
    prompt_version: str = 'phase3.v1'
    generation_mode: str = 'deterministic'
    preferred_model: str | None = None
    fallback_models: list[str] = Field(default_factory=list)
    response_schema: dict[str, Any] | None = None
    grounding: list[dict[str, Any]] = Field(default_factory=list)

class GenerateResponse(BaseModel):
    status: str
    ai_used: bool
    model: str | None = None
    routed_model: str | None = None
    prompt_name: str | None = None
    prompt_version_used: str | None = None
    generation_mode: str | None = None
    fallback_used: bool = False
    route_reason: str | None = None
    text: str
    latency_ms: int | None = None
    artifact_id: str | None = None
    validation_status: str = 'not_requested'
    grounding_source_refs: list[str] = Field(default_factory=list)

class EmbedRequest(BaseModel):
    input_text: str = Field(..., min_length=1)
    tenant_id: str = 'default'

class EmbedResponse(BaseModel):
    status: str
    model: str
    dimensions: int
    embedding: list[float]

class EnqueueRequest(BaseModel):
    tenant_id: str = 'default'
    actor_id: str | None = None
    job_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 5
    schedule_at: str | None = None
    max_retries: int = 3
    idempotency_key: str | None = None

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    retry_count: int
    max_retries: int
    result: dict[str, Any] | None = None
    last_error: str | None = None

class IngestNoteRequest(BaseModel):
    tenant_id: str = 'default'
    actor_id: str | None = None
    title: str | None = None
    body: str
    metadata: dict[str, Any] = Field(default_factory=dict)

class IngestPaperRequest(BaseModel):
    tenant_id: str = 'default'
    actor_id: str | None = None
    source_ref: str
    title: str | None = None
    body: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class IngestNoteResponse(BaseModel):
    status: str
    research_note_id: str | None = None
    paper_id: str | None = None
    chunks_created: int
    vector_mode: str = 'disabled'

class RetrieveRequest(BaseModel):
    tenant_id: str = 'default'
    actor_id: str | None = None
    query: str
    limit: int = 5
    metadata_filters: dict[str, Any] = Field(default_factory=dict)

class RetrieveItem(BaseModel):
    source_type: str
    source_ref: str | None = None
    title: str | None = None
    content: str
    score: float
    paper_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class RetrieveResponse(BaseModel):
    status: str
    mode: str
    count: int
    items: list[RetrieveItem]

class CommandRequest(BaseModel):
    tenant_id: str = 'default'
    actor_id: str = 'anonymous'
    channel: str = 'assistant'
    source: str = 'service'
    request_id: str | None = None
    text: str | None = None
    command: str
    args: str = ''

class CommandResponse(BaseModel):
    status: str
    command: str
    ai_used: bool = False
    model: str | None = None
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None

class ApprovalTransitionRequest(BaseModel):
    tenant_id: str = 'default'
    actor_id: str
    approval_id: str
    decision: Literal['approved', 'rejected']
    note: str | None = None

class ApprovalEvaluateRequest(BaseModel):
    tenant_id: str = 'default'
    actor_id: str
    domain: str
    action_type: str
    artifact_ref: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

class PublishBundleRequest(BaseModel):
    tenant_id: str = 'default'
    actor_id: str = 'anonymous'
    title: str = 'Publication bundle'
    summary_prompt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    require_approval: bool = True

class PublishBundleResponse(BaseModel):
    status: str
    publication_bundle_id: str
    release_artifact_id: str | None = None
    approval_id: str | None = None
    summary_artifact_id: str | None = None
    bundle_status: str
    included_posts: int = 0
    included_assets: int = 0
    included_approvals: int = 0

class MetricsResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    queue_depth: int
    queued_jobs: int
    running_jobs: int
    failed_jobs: int
    dead_letters: int
    pending_approvals: int
    ai_artifacts_24h: int
    avg_ai_latency_ms_24h: int | None = None
    published_posts: int = 0



class ConnectorCatalogItem(BaseModel):
    service_name: str
    display_name: str
    category: str
    integration_mode: str
    auth_type: str
    base_url_env: str
    base_url_placeholder: str
    required_credentials: list[str] = Field(default_factory=list)
    optional_credentials: list[str] = Field(default_factory=list)
    credential_placeholders: list[str] = Field(default_factory=list)
    supported_operations: list[dict[str, Any]] = Field(default_factory=list)
    input_schema_summary: dict[str, Any] = Field(default_factory=dict)
    output_schema_summary: dict[str, Any] = Field(default_factory=dict)
    rate_limit_retry_notes: str = ''
    implementation_status: str
    status: str | None = None
    notes: str = ''
    docs_reference: str | None = None

class ConnectorCatalogResponse(BaseModel):
    status: str
    count: int
    connectors: list[ConnectorCatalogItem]

class ConnectorPrepareRequest(BaseModel):
    service_name: str
    operation_id: str | None = None
    body: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, Any] = Field(default_factory=dict)

class ConnectorPrepareResponse(BaseModel):
    status: str
    prepared: dict[str, Any]
    codex_prompt: str

class WorkflowDraftRequest(BaseModel):
    service_name: str
    operation_id: str | None = None
    workflow_name: str | None = None

class WorkflowDraftResponse(BaseModel):
    status: str
    service_name: str
    operation_id: str
    workflow: dict[str, Any]
    codex_prompt: str

class ConnectorExecuteRequest(ConnectorPrepareRequest):
    timeout_seconds: int = 30

class ConnectorValidateConfigRequest(BaseModel):
    service_name: str

class ConnectorValidateConfigResponse(BaseModel):
    status: str
    service_name: str
    configured: bool
    missing_credentials: list[str] = Field(default_factory=list)
    present_credentials: list[str] = Field(default_factory=list)
    implementation_status: str
    integration_mode: str
    notes: str = ''

class ConnectorSmokeTestRequest(BaseModel):
    service_name: str
    operation_id: str | None = None
    dry_run: bool = True

class ConnectorSmokeTestResponse(BaseModel):
    status: str
    service_name: str
    operation_id: str
    dry_run: bool = True
    configured: bool
    missing_credentials: list[str] = Field(default_factory=list)
    implementation_status: str
    prepared: dict[str, Any] = Field(default_factory=dict)


class ConnectorPreflightRequest(BaseModel):
    tenant_id: str = 'default'
    service_names: list[str] = Field(default_factory=list)
    persist: bool = True

class ConnectorPreflightItem(BaseModel):
    service_name: str
    display_name: str
    configured: bool
    missing_credentials: list[str] = Field(default_factory=list)
    present_credentials: list[str] = Field(default_factory=list)
    implementation_status: str
    integration_mode: str
    supported_operations_count: int = 0
    recommended_operation_id: str | None = None
    live_ready: bool = False
    notes: str = ''
    base_url_env: str | None = None

class ConnectorPreflightResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    count: int
    configured_count: int
    live_ready_count: int
    connectors: list[ConnectorPreflightItem]

class ConnectorSyncRegistryRequest(BaseModel):
    tenant_id: str = 'default'

class ConnectorSyncRegistryResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    synced_count: int
    services: list[str] = Field(default_factory=list)


class ConnectorWorkflowManifestItem(BaseModel):
    service_name: str
    display_name: str
    implementation_status: str
    integration_mode: str
    supported_operations: list[str] = Field(default_factory=list)
    draftable_operations: list[str] = Field(default_factory=list)
    packaged_operations: list[str] = Field(default_factory=list)
    unpackaged_operations: list[str] = Field(default_factory=list)
    packaged_workflows: list[str] = Field(default_factory=list)
    operation_workflow_files: dict[str, list[str]] = Field(default_factory=dict)
    packaged_workflow_count: int = 0
    recommended_import_workflow: str | None = None
    recommended_draft_operation_id: str | None = None
    notes: str = ''


class ConnectorWorkflowManifestResponse(BaseModel):
    status: str
    count: int
    connectors: list[ConnectorWorkflowManifestItem]

class ConnectorReadinessReportRequest(BaseModel):
    tenant_id: str = 'default'
    service_names: list[str] = Field(default_factory=list)
    persist: bool = True


class ConnectorReadinessReportItem(BaseModel):
    service_name: str
    display_name: str
    configured: bool
    live_ready: bool
    implementation_status: str
    integration_mode: str
    missing_credentials: list[str] = Field(default_factory=list)
    present_credentials: list[str] = Field(default_factory=list)
    supported_operations_count: int = 0
    packaged_operations_count: int = 0
    packaged_workflow_count: int = 0
    packaged_coverage_percent: int = 0
    packaged_operations: list[str] = Field(default_factory=list)
    unpackaged_operations: list[str] = Field(default_factory=list)
    recommended_import_workflow: str | None = None
    recommended_operation_id: str | None = None
    recommended_draft_operation_id: str | None = None
    recommended_action: str
    notes: str = ''
    workflow_notes: str = ''
    base_url_env: str | None = None


class ConnectorReadinessReportResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    count: int
    configured_count: int
    live_ready_count: int
    import_ready_count: int
    draft_ready_count: int
    connectors: list[ConnectorReadinessReportItem]


class ConnectorDeploymentPlanRequest(BaseModel):
    tenant_id: str = 'default'
    service_names: list[str] = Field(default_factory=list)
    persist: bool = True


class ConnectorDeploymentPlanStep(BaseModel):
    order: int
    action: str
    detail: str
    required: bool = True
    workflow_name: str | None = None
    operation_id: str | None = None


class ConnectorDeploymentPlanItem(BaseModel):
    service_name: str
    display_name: str
    configured: bool
    live_ready: bool
    implementation_status: str
    integration_mode: str
    recommended_action: str
    primary_step: str
    recommended_import_workflow: str | None = None
    recommended_draft_operation_id: str | None = None
    smoke_operation_id: str | None = None
    missing_credentials: list[str] = Field(default_factory=list)
    packaged_coverage_percent: int = 0
    steps: list[ConnectorDeploymentPlanStep] = Field(default_factory=list)
    notes: str = ''
    workflow_notes: str = ''
    base_url_env: str | None = None


class ConnectorDeploymentPlanSummary(BaseModel):
    fill_credentials: int = 0
    import_packaged_workflow: int = 0
    use_workflow_draft: int = 0
    manual_bridge_review: int = 0
    docs_only_review: int = 0
    live_smoke_ready: int = 0


class ConnectorDeploymentPlanResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    count: int
    configured_count: int
    live_ready_count: int
    ready_to_import_count: int
    requires_credentials_count: int
    summary: ConnectorDeploymentPlanSummary
    connectors: list[ConnectorDeploymentPlanItem]
    next_actions: list[str] = Field(default_factory=list)




class ConnectorPersistenceReportRequest(BaseModel):
    tenant_id: str = 'default'


class ConnectorPersistenceTableItem(BaseModel):
    table_name: str
    exists: bool
    row_count: int | None = None
    last_validated_at: str | None = None
    note: str = ''


class ConnectorPersistenceReportResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    database_available: bool
    expected_table_count: int
    existing_table_count: int
    all_tables_present: bool
    connector_registry_count: int | None = None
    execution_log_count: int | None = None
    workflow_template_count: int | None = None
    smoke_test_count: int | None = None
    credential_meta_count: int | None = None
    recent_services: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    error: str | None = None
    tables: list[ConnectorPersistenceTableItem] = Field(default_factory=list)

class ConnectorRolloutBundleRequest(BaseModel):
    tenant_id: str = 'default'
    service_names: list[str] = Field(default_factory=list)
    persist: bool = True


class ConnectorRolloutBundleReportCounts(BaseModel):
    count: int = 0
    configured_count: int | None = None
    live_ready_count: int | None = None
    packaged_ready_count: int | None = None
    draftable_count: int | None = None
    import_ready_count: int | None = None
    draft_ready_count: int | None = None
    ready_to_import_count: int | None = None
    requires_credentials_count: int | None = None


class ConnectorRolloutBundleReports(BaseModel):
    preflight: ConnectorRolloutBundleReportCounts
    manifest: ConnectorRolloutBundleReportCounts
    readiness: ConnectorRolloutBundleReportCounts
    deployment: ConnectorRolloutBundleReportCounts


class ConnectorRolloutBundleItem(BaseModel):
    service_name: str
    display_name: str
    configured: bool
    live_ready: bool
    implementation_status: str
    integration_mode: str
    recommended_action: str
    primary_step: str
    recommended_import_workflow: str | None = None
    recommended_draft_operation_id: str | None = None
    smoke_operation_id: str | None = None
    missing_credentials: list[str] = Field(default_factory=list)
    present_credentials: list[str] = Field(default_factory=list)
    packaged_coverage_percent: int = 0
    packaged_workflows: list[str] = Field(default_factory=list)
    packaged_operations: list[str] = Field(default_factory=list)
    unpackaged_operations: list[str] = Field(default_factory=list)
    steps: list[ConnectorDeploymentPlanStep] = Field(default_factory=list)
    notes: str = ''
    workflow_notes: str = ''
    base_url_env: str | None = None


class ConnectorRolloutBundleResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    count: int
    configured_count: int
    live_ready_count: int
    ready_to_import_count: int
    requires_credentials_count: int
    summary: ConnectorDeploymentPlanSummary
    next_actions: list[str] = Field(default_factory=list)
    command_sequence: list[str] = Field(default_factory=list)
    reports: ConnectorRolloutBundleReports
    services: list[ConnectorRolloutBundleItem] = Field(default_factory=list)


class ConnectorCredentialMatrixRequest(BaseModel):
    tenant_id: str = 'default'
    service_names: list[str] = Field(default_factory=list)
    persist: bool = True


class ConnectorCredentialMatrixKeyItem(BaseModel):
    credential_key: str
    services: list[str] = Field(default_factory=list)
    required_by_services: list[str] = Field(default_factory=list)
    optional_for_services: list[str] = Field(default_factory=list)
    present_for_services: list[str] = Field(default_factory=list)
    missing_for_services: list[str] = Field(default_factory=list)
    configured_service_count: int = 0
    missing_service_count: int = 0
    all_required_services_ready: bool = False


class ConnectorCredentialMatrixServiceItem(BaseModel):
    service_name: str
    display_name: str
    configured: bool
    live_ready: bool
    implementation_status: str
    integration_mode: str
    required_credentials: list[str] = Field(default_factory=list)
    optional_credentials: list[str] = Field(default_factory=list)
    present_credentials: list[str] = Field(default_factory=list)
    missing_credentials: list[str] = Field(default_factory=list)
    base_url_env: str | None = None
    notes: str = ''


class ConnectorCredentialMatrixSummary(BaseModel):
    total_unique_credentials: int = 0
    fully_ready_credentials: int = 0
    partially_ready_credentials: int = 0
    missing_credentials: int = 0


class ConnectorCredentialMatrixResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    count: int
    configured_count: int
    live_ready_count: int
    unique_credential_key_count: int
    summary: ConnectorCredentialMatrixSummary
    next_actions: list[str] = Field(default_factory=list)
    services: list[ConnectorCredentialMatrixServiceItem] = Field(default_factory=list)
    credential_keys: list[ConnectorCredentialMatrixKeyItem] = Field(default_factory=list)

class AuthTokenRequest(BaseModel):
    username: str
    role: str | None = None
    tenant_id: str = 'default'


class AuthTokenResponse(BaseModel):
    status: str
    access_token: str
    token_type: str = 'bearer'
    expires_in_seconds: int
    user_id: str
    role: str
    tenant_id: str
    scopes: list[str] = Field(default_factory=list)


class SecretSetRequest(BaseModel):
    tenant_id: str = 'default'
    secret_name: str
    secret_value: str
    connector_binding: str | None = None


class SecretGetRequest(BaseModel):
    tenant_id: str = 'default'
    secret_name: str
    reveal: bool = False


class SecretListRequest(BaseModel):
    tenant_id: str = 'default'


class SecretItem(BaseModel):
    tenant_id: str = 'default'
    secret_name: str
    redacted_value: str | None = None
    value: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    updated_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SecretSetResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    secret_name: str
    redacted_value: str | None = None
    connector_binding: str | None = None


class SecretGetResponse(BaseModel):
    status: str
    secret: SecretItem


class SecretListResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    count: int
    secrets: list[SecretItem] = Field(default_factory=list)


class AdminSummaryResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    summary: dict[str, Any] = Field(default_factory=dict)


class ConnectorHealthResponse(BaseModel):
    status: str
    service_name: str
    configured: bool
    implementation_status: str
    integration_mode: str
    last_success_at: str | None = None
    last_failure_at: str | None = None
    failure_rate_percent: float = 0
    circuit_state: str = 'closed'
    circuit_open: bool = False
    blocked: bool = False
    consecutive_failures: int = 0
    failure_threshold: int | None = None
    requests_per_window: int | None = None
    window_seconds: int | None = None
    timeout_seconds: int | None = None
    cooldown_seconds: int | None = None
    rate_limit_rejection_count: int = 0
    circuit_open_count: int = 0
    timeout_rejection_count: int = 0
    notes: str = ''


class ConnectorMetricsResponse(BaseModel):
    status: str
    service_name: str
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    retry_count: int = 0
    blocked_count: int = 0
    rate_limit_rejection_count: int = 0
    circuit_open_count: int = 0
    timeout_rejection_count: int = 0
    failure_rate_percent: float = 0
    circuit_state: str = 'closed'
    consecutive_failures: int = 0
    requests_per_window: int | None = None
    window_seconds: int | None = None
    timeout_seconds: int | None = None
    cooldown_seconds: int | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_circuit_opened_at: str | None = None
    last_error_message: str | None = None


class ConnectorPolicyUpsertRequest(BaseModel):
    tenant_id: str = 'default'
    enabled: bool = True
    requests_per_window: int
    window_seconds: int
    timeout_seconds: int
    failure_threshold: int
    cooldown_seconds: int


class WorkflowExecutionPolicyRequest(BaseModel):
    tenant_id: str = 'default'
    workflow_id: str
    enabled: bool = True
    max_executions_per_window: int
    window_seconds: int


class WorkflowExecutionCheckRequest(BaseModel):
    tenant_id: str = 'default'
    workflow_id: str
    actor_id: str | None = None
    persist: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WorkflowExecutionCheckResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    workflow_id: str
    allowed: bool
    execution_count_window: int = 0
    remaining_executions: int = 0
    retry_after_seconds: int | None = None
    reason: str = ''
    policy: dict[str, Any] = Field(default_factory=dict)


class ConnectorFailureIsolationReportRequest(BaseModel):
    tenant_id: str = 'default'
    service_names: list[str] = Field(default_factory=list)
    persist: bool = True


class ConnectorFailureIsolationServiceItem(BaseModel):
    service_name: str
    display_name: str
    configured: bool
    implementation_status: str
    integration_mode: str
    circuit_state: str = 'closed'
    circuit_open: bool = False
    blocked: bool = False
    requests_per_window: int = 0
    window_seconds: int = 0
    timeout_seconds: int = 0
    failure_threshold: int = 0
    cooldown_seconds: int = 0
    recent_execute_count: int = 0
    consecutive_failures: int = 0
    rate_limit_rejection_count: int = 0
    circuit_open_count: int = 0
    timeout_rejection_count: int = 0
    recommended_action: str = ''
    notes: str = ''


class ConnectorFailureIsolationReportResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    count: int
    open_circuit_count: int
    half_open_count: int
    rate_limited_services_count: int
    next_actions: list[str] = Field(default_factory=list)
    services: list[ConnectorFailureIsolationServiceItem] = Field(default_factory=list)


class WorkflowVersionCreateRequest(BaseModel):
    tenant_id: str = 'default'
    workflow_id: str
    version: int
    definition_json: dict[str, Any] = Field(default_factory=dict)
    status: str = 'draft'


class WorkflowVersionPromoteRequest(BaseModel):
    tenant_id: str = 'default'
    workflow_id: str
    version: int
    status: str = 'published'


class WorkflowVersionResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    workflow_id: str
    version: int
    workflow_status: str
    definition_json: dict[str, Any] = Field(default_factory=dict)




class WorkflowVersionHistoryItem(BaseModel):
    workflow_id: str
    version: int
    workflow_status: str
    definition_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class WorkflowVersionHistoryResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    workflow_id: str
    count: int
    published_version: int | None = None
    versions: list[WorkflowVersionHistoryItem] = Field(default_factory=list)


class WorkflowVersionRollbackRequest(BaseModel):
    tenant_id: str = 'default'
    workflow_id: str
    source_version: int
    new_version: int | None = None
    status: str = 'draft'
    actor_id: str | None = None
    note: str | None = None

class RegistryListResponse(BaseModel):
    status: str
    count: int
    items: list[dict[str, Any]] = Field(default_factory=list)


class AIModelRegisterRequest(BaseModel):
    tenant_id: str = 'default'
    name: str
    type: str = 'local'
    capabilities: list[str] = Field(default_factory=list)
    latency_profile: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AIPromptRegisterRequest(BaseModel):
    tenant_id: str = 'default'
    name: str
    version: str
    template: str
    model_compatibility: list[str] = Field(default_factory=list)
    mode: str = 'deterministic'


class AIRouteRequest(BaseModel):
    tenant_id: str = 'default'
    action_type: str = 'fallback_chat'
    prompt_version: str | None = None
    generation_mode: str = 'deterministic'
    preferred_model: str | None = None
    fallback_models: list[str] = Field(default_factory=list)


class AIRouteResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    action_type: str
    generation_mode: str
    selected_model: str
    fallback_models: list[str] = Field(default_factory=list)
    attempted_models: list[str] = Field(default_factory=list)
    prompt_name: str
    prompt_version: str
    prompt_mode: str = 'deterministic'
    route_reason: str = ''
    source: str = 'fallback'
    available_models: list[str] = Field(default_factory=list)
    available_prompts: list[str] = Field(default_factory=list)


class RAGDocumentIngestRequest(BaseModel):
    tenant_id: str = 'default'
    actor_id: str | None = None
    source_ref: str
    title: str | None = None
    body: str
    mime_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding_model: str | None = None


class RAGDocumentIngestResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    source_ref: str
    document_id: str | None = None
    chunks_created: int = 0
    vector_mode: str = 'lexical'
    embedding_model: str | None = None


class RAGGovernanceResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    document_count: int = 0
    chunk_count: int = 0
    embedding_version_count: int = 0
    recent_documents: list[dict[str, Any]] = Field(default_factory=list)
    latest_embedding_models: list[dict[str, Any]] = Field(default_factory=list)


class ReleaseManifestRequest(BaseModel):
    tenant_id: str = 'default'
    release_version: str | None = None
    package_filename: str | None = None
    source_package: str | None = None
    created_by: str | None = None
    persist: bool = True


class ReleaseManifestResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    release_version: str
    package_filename: str | None = None
    source_package: str | None = None
    generated_at: str
    checksum_algorithm: str = 'sha256'
    manifest_checksum: str
    file_count: int = 0
    workflow_count: int = 0
    migration_count: int = 0
    checksums: dict[str, str] = Field(default_factory=dict)
    includes: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)


class ReleaseChecksumValidateRequest(BaseModel):
    tenant_id: str = 'default'
    release_version: str | None = None
    manifest_json: dict[str, Any] | None = None
    persist: bool = True


class ReleaseChecksumValidationResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    release_version: str
    valid: bool
    checksum_algorithm: str = 'sha256'
    manifest_checksum: str
    validated_file_count: int = 0
    mismatch_count: int = 0
    missing_count: int = 0
    mismatched_files: list[str] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class ReleaseRollbackPackageRequest(BaseModel):
    tenant_id: str = 'default'
    release_version: str | None = None
    package_filename: str | None = None
    source_package: str | None = None
    output_path: str | None = None
    created_by: str | None = None
    persist: bool = True


class ReleaseRollbackPackageResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    release_version: str
    output_path: str
    package_checksum: str
    included_files_count: int = 0
    manifest_path: str | None = None
    includes: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class ReleasePreflightRequest(BaseModel):
    tenant_id: str = 'default'
    release_version: str | None = None
    persist: bool = True


class ReleasePreflightResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    release_version: str
    ready: bool
    workflow_count: int = 0
    migration_count: int = 0
    generated_artifacts: list[str] = Field(default_factory=list)
    checks: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)

class ReleasePublishRequest(BaseModel):
    tenant_id: str = 'default'
    release_version: str | None = None
    package_filename: str | None = None
    source_package: str | None = None
    output_path: str | None = None
    created_by: str | None = None
    persist: bool = True
    require_preflight: bool = True
    require_checksum_validation: bool = True
    include_reports: bool = True


class ReleasePublishResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    release_version: str
    published: bool
    publication_status: str
    output_path: str
    package_checksum: str
    included_files_count: int = 0
    manifest_checksum: str
    preflight_ready: bool = False
    checksum_valid: bool = False
    generated_artifacts: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class ReleasePublicationItem(BaseModel):
    tenant_id: str = 'default'
    release_version: str
    publication_status: str
    package_path: str | None = None
    package_checksum: str | None = None
    manifest_checksum: str | None = None
    created_by: str | None = None
    created_at: Any | None = None
    publication_json: dict[str, Any] = Field(default_factory=dict)


class ReleasePublicationListResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    count: int = 0
    items: list[ReleasePublicationItem] = Field(default_factory=list)

class ReleaseChannelUpsertRequest(BaseModel):
    tenant_id: str = 'default'
    channel_name: str
    channel_type: str
    enabled: bool = True
    destination_path: str | None = None
    endpoint_url: str | None = None
    auth_secret_ref: str | None = None
    created_by: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReleaseChannelItem(BaseModel):
    tenant_id: str = 'default'
    channel_name: str
    channel_type: str
    enabled: bool = True
    destination_path: str | None = None
    endpoint_url: str | None = None
    auth_secret_ref: str | None = None
    auth_secret_configured: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    last_planned_at: Any | None = None
    last_published_at: Any | None = None
    created_at: Any | None = None
    updated_at: Any | None = None
    source: str = 'db'


class ReleaseChannelResponse(BaseModel):
    status: str
    channel: ReleaseChannelItem


class ReleaseChannelListResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    count: int = 0
    items: list[ReleaseChannelItem] = Field(default_factory=list)


class ReleaseChannelPlanRequest(BaseModel):
    tenant_id: str = 'default'
    release_version: str | None = None
    package_filename: str | None = None
    source_package: str | None = None
    include_publication_bundle: bool = False
    output_path: str | None = None
    created_by: str | None = None
    persist: bool = True


class ReleaseChannelPlanItem(BaseModel):
    channel_name: str
    channel_type: str
    enabled: bool = True
    ready: bool = False
    publication_ready: bool = False
    requires_publication_bundle: bool = True
    destination: str | None = None
    auth_secret_configured: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)
    recommended_action: str = ''
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReleaseChannelPlanResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    release_version: str
    publication_ready: bool = False
    bundle_preview_path: str | None = None
    count: int = 0
    ready_count: int = 0
    planned_channels: list[ReleaseChannelPlanItem] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)



class ReleaseChannelExecuteRequest(BaseModel):
    tenant_id: str = 'default'
    release_version: str | None = None
    package_filename: str | None = None
    source_package: str | None = None
    channel_names: list[str] = Field(default_factory=list)
    include_publication_bundle: bool = True
    output_path: str | None = None
    created_by: str | None = None
    persist: bool = True
    dry_run: bool = True
    execute_webhooks: bool = False


class ReleaseChannelExecutionItem(BaseModel):
    channel_name: str
    channel_type: str
    execution_mode: str
    status: str
    dry_run: bool = True
    ready: bool = False
    publication_ready: bool = False
    delivery_ref: str | None = None
    output_path: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReleaseChannelExecuteResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    release_version: str
    publication_ready: bool = False
    bundle_path: str | None = None
    count: int = 0
    delivered_count: int = 0
    prepared_count: int = 0
    blocked_count: int = 0
    execution_items: list[ReleaseChannelExecutionItem] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class ReleaseChannelExecutionRecord(BaseModel):
    tenant_id: str = 'default'
    channel_name: str
    release_version: str
    execution_mode: str
    execution_status: str
    dry_run: bool = True
    package_path: str | None = None
    output_path: str | None = None
    delivery_ref: str | None = None
    created_by: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    started_at: Any | None = None
    finished_at: Any | None = None
    created_at: Any | None = None


class ReleaseChannelExecutionListResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    count: int = 0
    items: list[ReleaseChannelExecutionRecord] = Field(default_factory=list)



class LifecyclePolicyUpsertRequest(BaseModel):
    tenant_id: str = 'default'
    resource_type: str
    enabled: bool = True
    retain_days: int = 30
    archive_before_delete: bool = False
    batch_size: int = 500
    updated_by: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class LifecyclePolicyItem(BaseModel):
    tenant_id: str = 'default'
    resource_type: str
    enabled: bool = True
    retain_days: int = 30
    archive_before_delete: bool = False
    batch_size: int = 500
    last_run_at: Any | None = None
    updated_by: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None


class LifecyclePolicyResponse(BaseModel):
    status: str
    policy: LifecyclePolicyItem


class DataLifecycleReportRequest(BaseModel):
    tenant_id: str = 'default'
    resource_types: list[str] = Field(default_factory=list)
    persist: bool = False


class DataLifecycleReportItem(BaseModel):
    resource_type: str
    enabled: bool = True
    retain_days: int = 30
    archive_before_delete: bool = False
    batch_size: int = 500
    total_count: int = 0
    eligible_count: int = 0
    last_run_at: Any | None = None
    updated_by: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    next_action: str | None = None


class DataLifecycleReportResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    count: int = 0
    eligible_total: int = 0
    report_generated_at: str | None = None
    policies: list[DataLifecycleReportItem] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class DataLifecycleCleanupRequest(BaseModel):
    tenant_id: str = 'default'
    actor_id: str | None = None
    resource_types: list[str] = Field(default_factory=list)
    dry_run: bool = True
    persist: bool = True


class DataLifecycleCleanupItem(BaseModel):
    resource_type: str
    enabled: bool = True
    retain_days: int = 30
    archive_before_delete: bool = False
    batch_size: int = 500
    total_count: int = 0
    eligible_count: int = 0
    archived_count: int = 0
    deleted_count: int = 0
    dry_run: bool = True
    last_run_at: Any | None = None


class DataLifecycleCleanupResponse(BaseModel):
    status: str
    tenant_id: str = 'default'
    dry_run: bool = True
    count: int = 0
    eligible_total: int = 0
    archived_total: int = 0
    deleted_total: int = 0
    items: list[DataLifecycleCleanupItem] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class TenantCreateRequest(BaseModel):
    tenant_id: str
    tenant_name: str | None = None
    created_by: str | None = None


class TenantCreateResponse(BaseModel):
    status: str
    tenant_id: str
    tenant_name: str
    created_by: str | None = None


class TenantMembershipUpsertRequest(BaseModel):
    tenant_id: str = 'default'
    actor_id: str
    role_name: str = 'viewer'
    created_by: str | None = None
    username: str | None = None
    display_name: str | None = None
    is_default: bool = False
    is_active: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantMembershipItem(BaseModel):
    tenant_id: str
    tenant_name: str | None = None
    actor_id: str
    role_name: str
    is_default: bool = False
    is_active: bool = True
    created_by: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantMembershipUpsertResponse(BaseModel):
    status: str
    membership: TenantMembershipItem


class TenantContextResponse(BaseModel):
    status: str
    tenant_id: str
    requested_tenant_id: str
    effective_tenant_id: str
    actor_id: str
    role: str
    identity_tenant_id: str
    strict_enforcement: bool = False
    admin_override_enabled: bool = False
    has_access: bool = True
    resolution_mode: str = 'requested'
    membership_count: int = 0
    memberships: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class TenantPolicyUpsertRequest(BaseModel):
    tenant_id: str = 'default'
    route_prefix: str
    resource_type: str = 'generic'
    strict_mode: Literal['inherit', 'enforce', 'relaxed'] = 'inherit'
    require_membership: bool = True
    allow_admin_override: bool = True
    allow_service_account_override: bool = False
    updated_by: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantPolicyItem(BaseModel):
    tenant_id: str = 'default'
    route_prefix: str
    resource_type: str
    strict_mode: str = 'inherit'
    require_membership: bool = True
    allow_admin_override: bool = True
    allow_service_account_override: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    updated_by: str | None = None


class TenantPolicyUpsertResponse(BaseModel):
    status: str
    policy: TenantPolicyItem


class TenantEnforcementReportRequest(BaseModel):
    tenant_id: str = 'default'
    route: str = '/connectors/catalog'
    method: str = 'GET'
    actor_id: str = 'anonymous'
    role: str = 'viewer'
    identity_tenant_id: str = 'default'
    requested_tenant_id: str | None = None


class TenantEnforcementReportResponse(BaseModel):
    status: str
    tenant_id: str
    requested_tenant_id: str
    effective_tenant_id: str
    actor_id: str
    role: str
    identity_tenant_id: str
    route: str
    method: str
    decision: str
    reason: str
    strict_enforcement: bool = False
    policy: TenantPolicyItem
    membership_count: int = 0
    memberships: list[dict[str, Any]] = Field(default_factory=list)
    accessible_tenants: list[str] = Field(default_factory=list)
    policy_count: int = 0
    policies: list[TenantPolicyItem] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class TenantRowPolicyUpsertRequest(BaseModel):
    tenant_id: str = 'default'
    resource_table: str
    strict_mode: Literal['inherit', 'enforce', 'relaxed'] = 'inherit'
    require_tenant_match: bool = True
    allow_admin_override: bool = True
    allow_service_account_override: bool = False
    allow_global_rows: bool = False
    updated_by: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantRowPolicyItem(BaseModel):
    tenant_id: str = 'default'
    resource_table: str
    strict_mode: str = 'inherit'
    require_tenant_match: bool = True
    allow_admin_override: bool = True
    allow_service_account_override: bool = False
    allow_global_rows: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    updated_by: str | None = None


class TenantRowPolicyUpsertResponse(BaseModel):
    status: str
    policy: TenantRowPolicyItem


class TenantRowIsolationReportRequest(BaseModel):
    tenant_id: str = 'default'
    resource_table: str = 'jobs'
    action: str = 'read'
    actor_id: str = 'anonymous'
    role: str = 'viewer'
    identity_tenant_id: str = 'default'
    requested_tenant_id: str | None = None


class TenantRowIsolationReportResponse(BaseModel):
    status: str
    tenant_id: str
    requested_tenant_id: str
    effective_tenant_id: str
    actor_id: str
    role: str
    identity_tenant_id: str
    resource_table: str
    action: str
    decision: str
    reason: str
    strict_enforcement: bool = False
    policy: TenantRowPolicyItem
    membership_count: int = 0
    memberships: list[dict[str, Any]] = Field(default_factory=list)
    accessible_tenants: list[str] = Field(default_factory=list)
    policy_count: int = 0
    policies: list[TenantRowPolicyItem] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class TenantQueryScopeReportRequest(BaseModel):
    tenant_id: str = 'default'
    resource_table: str = 'release_publications'
    route: str = '/release/publications'
    action: str = 'read'
    actor_id: str = 'anonymous'
    role: str = 'viewer'
    identity_tenant_id: str = 'default'
    requested_tenant_id: str | None = None


class TenantQueryScopeReportResponse(BaseModel):
    status: str
    tenant_id: str
    requested_tenant_id: str
    effective_tenant_id: str
    actor_id: str
    role: str
    identity_tenant_id: str
    resource_table: str
    route: str
    action: str
    decision: str
    reason: str
    strict_enforcement: bool = False
    policy: TenantRowPolicyItem
    visible_tenant_ids: list[str] = Field(default_factory=list)
    query_scope_sql: str = ''
    records_before: int = 0
    records_after: int = 0
    filtered_count: int = 0
    policy_count: int = 0
    policies: list[TenantRowPolicyItem] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class TenantQueryCoverageTargetRequest(BaseModel):
    tenant_id: str = 'default'
    route: str
    resource_table: str
    action: str = 'read'
    strict_mode: Literal['inherit', 'enforce', 'relaxed'] = 'inherit'
    notes: str | None = None
    updated_by: str | None = None


class TenantQueryCoverageTargetItem(BaseModel):
    tenant_id: str = 'default'
    route: str
    resource_table: str
    action: str = 'read'
    strict_mode: str = 'inherit'
    notes: str | None = None
    source: str | None = None
    updated_by: str | None = None


class TenantQueryCoverageTargetResponse(BaseModel):
    status: str
    target: TenantQueryCoverageTargetItem


class TenantQueryCoverageReportRequest(BaseModel):
    tenant_id: str = 'default'
    actor_id: str = 'anonymous'
    role: str = 'viewer'
    identity_tenant_id: str = 'default'
    requested_tenant_id: str | None = None


class TenantQueryCoverageReportResponse(BaseModel):
    status: str
    tenant_id: str
    requested_tenant_id: str
    effective_tenant_id: str
    actor_id: str
    role: str
    identity_tenant_id: str
    target_count: int = 0
    covered_count: int = 0
    strict_target_count: int = 0
    targets: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
