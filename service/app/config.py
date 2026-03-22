
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    database_url: str = Field(default='postgresql://postgres:postgres@postgres:5432/control_plane')
    ollama_base_url: str = Field(default='http://ollama:11434')
    ollama_model: str = Field(default='gemma3')
    ollama_embedding_model: str = Field(default='embeddinggemma')
    queue_poll_seconds: int = Field(default=5)
    worker_id: str = Field(default='phase2-worker-1')
    lease_seconds: int = Field(default=180)
    service_base_url: str = Field(default='http://service:8000')
    retrieval_limit: int = Field(default=6)
    fallback_chat_system_prompt: str = Field(default='You are a grounded local assistant. Use provided context when available. If evidence is weak, say so plainly.')
    connector_timeout_seconds: int = Field(default=30)
    workspace_export_dir: str = Field(default='/data/exports')

    auth_required: bool = Field(default=False)
    jwt_secret: str = Field(default='change-me-enterprise-jwt-secret')
    jwt_issuer: str = Field(default='hybrid-control-plane')
    jwt_expiry_seconds: int = Field(default=3600)
    auth_bootstrap_users_raw: str = Field(default='admin:admin,operator:operator,viewer:viewer,svc:service_account')
    secret_encryption_key: str = Field(default='')
    enable_idempotency: bool = Field(default=True)
    log_json: bool = Field(default=True)
    correlation_header_name: str = Field(default='x-correlation-id')
    queue_backend: str = Field(default='db')
    redis_url: str = Field(default='redis://redis:6379/0')
    queue_backend_namespace: str = Field(default='controlplane')
    worker_concurrency: int = Field(default=4)
    queue_max_claim_batch: int = Field(default=16)
    retry_backoff_base_seconds: int = Field(default=15)
    retry_backoff_max_seconds: int = Field(default=1800)
    retry_backoff_jitter_seconds: int = Field(default=5)
    connector_rate_limit_window_seconds: int = Field(default=60)
    connector_rate_limit_max_requests: int = Field(default=30)
    connector_circuit_breaker_threshold: int = Field(default=5)
    connector_circuit_breaker_reset_seconds: int = Field(default=300)
    connector_timeout_cap_seconds: int = Field(default=90)
    workflow_execution_cap_window_seconds: int = Field(default=60)
    workflow_execution_cap_max_requests: int = Field(default=120)
    release_artifact_dir: str = Field(default='')
    release_channel_default_type: str = Field(default='manual_inspection')
    release_channel_default_destination: str = Field(default='artifacts/release_channel_drops')
    release_channel_execution_dir: str = Field(default='artifacts/release_channel_executions')
    release_channel_execute_webhooks: bool = Field(default=False)
    lifecycle_default_retain_days: int = Field(default=30)
    lifecycle_cleanup_batch_size: int = Field(default=500)
    lifecycle_archive_dead_letters: bool = Field(default=True)
    tenant_default_id: str = Field(default='default')
    strict_tenant_enforcement: bool = Field(default=False)
    tenant_header_name: str = Field(default='x-tenant-id')
    tenant_allow_admin_override: bool = Field(default=True)
    tenant_policy_default_strict_mode: str = Field(default='inherit')
    tenant_policy_default_require_membership: bool = Field(default=True)
    tenant_policy_audit_enabled: bool = Field(default=True)
    strict_tenant_row_isolation: bool = Field(default=False)
    tenant_row_policy_default_strict_mode: str = Field(default='inherit')
    tenant_row_policy_default_require_tenant_match: bool = Field(default=True)


    @property
    def auth_bootstrap_users(self) -> dict:
        users = {}
        for item in self.auth_bootstrap_users_raw.split(','):
            if not item.strip() or ':' not in item:
                continue
            username, role = item.split(':', 1)
            users[username.strip()] = {'user_id': username.strip(), 'role': role.strip()}
        return users

settings = Settings()
