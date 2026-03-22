from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / 'service'
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from app.connectors import catalog_rows_for_sync
from app.db import execute


UPSERT_SQL = """
INSERT INTO connector_registry (tenant_id, service_name, category, integration_mode, auth_type, base_url_env, required_credentials, optional_credentials, implementation_status, notes, docs_reference)
VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
ON CONFLICT (tenant_id, service_name)
DO UPDATE SET category=EXCLUDED.category, integration_mode=EXCLUDED.integration_mode, auth_type=EXCLUDED.auth_type, base_url_env=EXCLUDED.base_url_env, required_credentials=EXCLUDED.required_credentials, optional_credentials=EXCLUDED.optional_credentials, implementation_status=EXCLUDED.implementation_status, notes=EXCLUDED.notes, docs_reference=EXCLUDED.docs_reference, updated_at=now()
"""


def main() -> None:
    tenant_id = sys.argv[1] if len(sys.argv) > 1 else 'default'
    rows = catalog_rows_for_sync(tenant_id=tenant_id)
    for row in rows:
        execute(
            UPSERT_SQL,
            (
                row['tenant_id'],
                row['service_name'],
                row['category'],
                row['integration_mode'],
                row['auth_type'],
                row['base_url_env'],
                json.dumps(row.get('required_credentials', [])),
                json.dumps(row.get('optional_credentials', [])),
                row['implementation_status'],
                row.get('notes', ''),
                row.get('docs_reference'),
            ),
        )
    print(json.dumps({'status': 'ok', 'tenant_id': tenant_id, 'synced_count': len(rows), 'services': [row['service_name'] for row in rows]}, indent=2))


if __name__ == '__main__':
    main()
