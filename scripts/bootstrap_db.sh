#!/usr/bin/env bash
set -euo pipefail
psql "$DATABASE_URL" -f sql/unified_production_schema_v2.sql
for m in migrations/*.sql; do psql "$DATABASE_URL" -f "$m"; done
