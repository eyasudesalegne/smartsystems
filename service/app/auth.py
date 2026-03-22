from __future__ import annotations
import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status

from .config import settings
from .db import fetch_all, fetch_one, execute

ROLE_SCOPE_MAP = {
    'admin': {'workflows:read', 'workflows:write', 'connectors:read', 'connectors:write', 'jobs:read', 'jobs:write', 'system:read', 'system:write', 'secrets:read', 'secrets:write', 'admin:read', 'tenants:read', 'tenants:write'},
    'operator': {'workflows:read', 'workflows:write', 'connectors:read', 'connectors:write', 'jobs:read', 'jobs:write', 'system:read', 'secrets:read', 'tenants:read'},
    'viewer': {'workflows:read', 'connectors:read', 'jobs:read', 'system:read', 'tenants:read'},
    'service_account': {'workflows:read', 'workflows:write', 'connectors:read', 'connectors:write', 'jobs:read', 'jobs:write', 'system:read', 'system:write', 'secrets:read', 'tenants:read', 'tenants:write'},
}

RESOURCE_SCOPE_RULES = [
    ('/admin/', 'admin:read'),
    ('/secrets/', 'secrets:read'),
    ('/connectors/', 'connectors:read'),
    ('/jobs/', 'jobs:read'),
    ('/publishbundle/', 'workflows:write'),
    ('/command/', 'workflows:write'),
    ('/approvals/', 'workflows:write'),
    ('/ingest/', 'workflows:write'),
    ('/retrieve/', 'workflows:read'),
    ('/ai/', 'system:read'),
    ('/rag/', 'workflows:read'),
    ('/workflows/', 'workflows:read'),
    ('/release/', 'system:read'),
    ('/metrics', 'system:read'),
    ('/ready', 'system:read'),
    ('/health', 'system:read'),
    ('/tenants/', 'tenants:read'),
]
WRITE_SCOPE_OVERRIDES = {
    '/connectors/': 'connectors:write',
    '/jobs/': 'jobs:write',
    '/secrets/': 'secrets:write',
    '/admin/': 'admin:read',
    '/publishbundle/': 'workflows:write',
    '/command/': 'workflows:write',
    '/approvals/': 'workflows:write',
    '/ingest/': 'workflows:write',
    '/ai/': 'system:write',
    '/rag/': 'workflows:write',
    '/workflows/': 'workflows:write',
    '/release/': 'system:write',
    '/tenants/': 'tenants:write',
}

@dataclass
class Identity:
    user_id: str
    tenant_id: str
    role: str
    scopes: list[str]
    subject: str
    token_type: str = 'access'


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(message: bytes, secret: str) -> str:
    return _b64url_encode(hmac.new(secret.encode(), message, hashlib.sha256).digest())


def issue_token(user_id: str, role: str, tenant_id: str = 'default', scopes: list[str] | None = None, expires_in_seconds: int | None = None) -> str:
    header = {'alg': 'HS256', 'typ': 'JWT'}
    scopes = scopes or sorted(ROLE_SCOPE_MAP.get(role, set()))
    now = int(time.time())
    payload = {
        'sub': user_id,
        'user_id': user_id,
        'tenant_id': tenant_id,
        'role': role,
        'scopes': scopes,
        'iat': now,
        'exp': now + (expires_in_seconds or settings.jwt_expiry_seconds),
        'iss': settings.jwt_issuer,
    }
    signing_input = f"{_b64url_encode(json.dumps(header, separators=(',', ':')).encode())}.{_b64url_encode(json.dumps(payload, separators=(',', ':')).encode())}".encode()
    signature = _sign(signing_input, settings.jwt_secret)
    return signing_input.decode() + '.' + signature


def decode_token(token: str) -> Identity:
    try:
        header_b64, payload_b64, signature = token.split('.')
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid_token') from exc
    signing_input = f'{header_b64}.{payload_b64}'.encode()
    expected = _sign(signing_input, settings.jwt_secret)
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid_signature')
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode())
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid_payload') from exc
    if payload.get('iss') != settings.jwt_issuer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid_issuer')
    if int(payload.get('exp', 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='token_expired')
    return Identity(
        user_id=payload.get('user_id') or payload.get('sub') or 'unknown',
        tenant_id=payload.get('tenant_id') or 'default',
        role=payload.get('role') or 'viewer',
        scopes=list(payload.get('scopes') or []),
        subject=payload.get('sub') or 'unknown',
    )


def authenticate_request(request: Request) -> Identity:
    auth_header = request.headers.get('authorization', '')
    if not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='missing_bearer_token')
    token = auth_header.split(' ', 1)[1].strip()
    identity = decode_token(token)
    request.state.identity = identity
    request.state.tenant_id = identity.tenant_id
    request.state.actor_id = identity.user_id
    return identity


def required_scope_for_request(request: Request) -> str | None:
    path = request.url.path
    method = request.method.upper()
    for prefix, scope in RESOURCE_SCOPE_RULES:
        if path.startswith(prefix) or path == prefix.rstrip('/'):
            if method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
                return WRITE_SCOPE_OVERRIDES.get(prefix, scope)
            return scope
    return 'system:read'


def authorize_request(request: Request, identity: Identity | None) -> None:
    if identity is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='unauthenticated')
    required_scope = required_scope_for_request(request)
    if required_scope and required_scope not in set(identity.scopes):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={'required_scope': required_scope, 'role': identity.role})


def list_effective_scopes(role: str) -> list[str]:
    return sorted(ROLE_SCOPE_MAP.get(role, set()))


def seed_rbac_defaults(tenant_id: str = 'default') -> None:
    try:
        execute("INSERT INTO tenants (tenant_id, tenant_name) VALUES (%s, %s) ON CONFLICT (tenant_id) DO NOTHING", (tenant_id, tenant_id.title()))
        for role_name, scopes in ROLE_SCOPE_MAP.items():
            execute("INSERT INTO roles (tenant_id, role_name) VALUES (%s, %s) ON CONFLICT (tenant_id, role_name) DO NOTHING", (tenant_id, role_name))
            for scope_name in scopes:
                execute("INSERT INTO scopes (scope_name) VALUES (%s) ON CONFLICT (scope_name) DO NOTHING", (scope_name,))
                row = fetch_one("SELECT role_id FROM roles WHERE tenant_id=%s AND role_name=%s", (tenant_id, role_name))
                scope = fetch_one("SELECT scope_id FROM scopes WHERE scope_name=%s", (scope_name,))
                if row and scope:
                    execute("INSERT INTO role_scopes (role_id, scope_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (row['role_id'], scope['scope_id']))
    except Exception:
        pass


def resolve_bootstrap_user(username: str, tenant_id: str = 'default') -> dict[str, Any] | None:
    configured = settings.auth_bootstrap_users
    if username in configured:
        user = dict(configured[username])
        user.setdefault('tenant_id', tenant_id)
        user.setdefault('user_id', username)
        user.setdefault('role', 'admin')
        return user
    return None


def write_request_audit(user_id: str | None, action: str, resource_type: str, resource_id: str | None, metadata_json: dict[str, Any] | None = None, tenant_id: str = 'default') -> None:
    try:
        execute(
            """INSERT INTO audit_logs (tenant_id, user_id, action, resource_type, resource_id, metadata_json, timestamp)
            VALUES (%s,%s,%s,%s,%s,%s::jsonb,now())""",
            (tenant_id, user_id, action, resource_type, resource_id, json.dumps(metadata_json or {})),
        )
    except Exception:
        pass
