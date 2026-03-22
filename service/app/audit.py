
import json
from .db import execute, fetch_one


def write_audit(request_id: str, tenant_id: str, actor_id: str | None, source: str, channel: str, route: str, domain: str, command: str, decision: str, status: str, ai_used: bool = False, ai_model: str | None = None, ai_action_type: str | None = None, ai_latency_ms: int | None = None, error_code: str | None = None, error_message: str | None = None, grounding_source_refs=None):
    execute(
        """INSERT INTO audits (
            request_id, tenant_id, actor_id, source, channel, route, domain, command, decision,
            started_at, completed_at, status, error_code, error_message, ai_used, ai_model,
            ai_action_type, ai_latency_ms, grounding_source_refs
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now(),%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
        (request_id, tenant_id, actor_id, source, channel, route, domain, command, decision, status,
         error_code, error_message, ai_used, ai_model, ai_action_type, ai_latency_ms, json.dumps(grounding_source_refs or [])),
    )


def enforce_scope(tenant_id: str, actor_id: str | None, scope_name: str) -> bool:
    if not actor_id:
        return False
    row = fetch_one(
        """SELECT 1 AS ok
           FROM actor_roles ar
           JOIN role_scopes rs ON rs.role_id = ar.role_id
           JOIN scopes s ON s.scope_id = rs.scope_id
           WHERE ar.actor_id = %s AND ar.tenant_id = %s AND s.scope_name = %s
           LIMIT 1""",
        (actor_id, tenant_id, scope_name),
    )
    return bool(row)
