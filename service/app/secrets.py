from __future__ import annotations
import base64
import hashlib
import json
import os
from typing import Any

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover
    Fernet = None
    InvalidToken = Exception

from .config import settings
from .db import execute, fetch_all, fetch_one


def _derive_fernet_key() -> bytes:
    raw = settings.secret_encryption_key.strip()
    if raw:
        try:
            if len(raw) == 44:
                base64.urlsafe_b64decode(raw.encode())
                return raw.encode()
        except Exception:
            pass
    digest = hashlib.sha256((raw or settings.jwt_secret).encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _get_cipher():
    if Fernet is None:
        raise RuntimeError('cryptography.fernet unavailable')
    return Fernet(_derive_fernet_key())


def redact_secret(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) <= 6:
        return '***'
    return value[:2] + '***' + value[-2:]


def encrypt_secret(value: str) -> str:
    return _get_cipher().encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _get_cipher().decrypt(token.encode()).decode()


def set_secret(secret_name: str, secret_value: str, tenant_id: str = 'default', created_by: str | None = None, connector_binding: str | None = None) -> dict[str, Any]:
    encrypted = encrypt_secret(secret_value)
    metadata = {'connector_binding': connector_binding} if connector_binding else {}
    execute(
        """INSERT INTO secrets_store (tenant_id, secret_name, encrypted_value, created_by, updated_by, metadata_json)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (tenant_id, secret_name)
        DO UPDATE SET encrypted_value=EXCLUDED.encrypted_value, updated_by=EXCLUDED.updated_by, metadata_json=EXCLUDED.metadata_json, updated_at=now()""",
        (tenant_id, secret_name, encrypted, created_by, created_by, json.dumps(metadata)),
    )
    return {'status': 'ok', 'tenant_id': tenant_id, 'secret_name': secret_name, 'redacted_value': redact_secret(secret_value), 'connector_binding': connector_binding}


def get_secret(secret_name: str, tenant_id: str = 'default', reveal: bool = False) -> dict[str, Any] | None:
    row = fetch_one("SELECT tenant_id, secret_name, encrypted_value, created_by, updated_by, created_at, updated_at, metadata_json FROM secrets_store WHERE tenant_id=%s AND secret_name=%s", (tenant_id, secret_name))
    if not row:
        return None
    value = decrypt_secret(row['encrypted_value'])
    return {
        'tenant_id': row['tenant_id'],
        'secret_name': row['secret_name'],
        'value': value if reveal else None,
        'redacted_value': redact_secret(value),
        'created_by': row.get('created_by'),
        'updated_by': row.get('updated_by'),
        'created_at': row.get('created_at').isoformat() if row.get('created_at') else None,
        'updated_at': row.get('updated_at').isoformat() if row.get('updated_at') else None,
        'metadata': row.get('metadata_json') or {},
    }


def list_secrets(tenant_id: str = 'default') -> dict[str, Any]:
    try:
        rows = fetch_all("SELECT tenant_id, secret_name, created_by, updated_by, created_at, updated_at, metadata_json FROM secrets_store WHERE tenant_id=%s ORDER BY secret_name", (tenant_id,))
    except Exception:
        rows = []
    return {
        'status': 'ok',
        'tenant_id': tenant_id,
        'count': len(rows),
        'secrets': [
            {
                'tenant_id': row['tenant_id'],
                'secret_name': row['secret_name'],
                'created_by': row.get('created_by'),
                'updated_by': row.get('updated_by'),
                'created_at': row.get('created_at').isoformat() if row.get('created_at') else None,
                'updated_at': row.get('updated_at').isoformat() if row.get('updated_at') else None,
                'metadata': row.get('metadata_json') or {},
            }
            for row in rows
        ],
    }


def resolve_secret_reference(value: str | None, tenant_id: str = 'default') -> str | None:
    if not value:
        return value
    if not isinstance(value, str) or not value.startswith('secret:'):
        return value
    secret_name = value.split(':', 1)[1].strip()
    if not secret_name:
        return ''
    try:
        resolved = get_secret(secret_name, tenant_id=tenant_id, reveal=True)
    except Exception:
        return ''
    return resolved['value'] if resolved else ''
