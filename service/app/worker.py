import json
import logging
import random
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Any

try:  # pragma: no cover - optional dependency path
    import redis as redis_lib
except Exception:  # pragma: no cover - optional dependency path
    redis_lib = None

from .config import settings
from .db import execute, fetch_one, get_conn

logger = logging.getLogger('control_plane.worker')

CLAIM_SQL = """
WITH recovered AS (
  UPDATE queue_items
  SET status='queued', lease_until=NULL, available_at=now(), updated_at=now(), claimed_at=NULL, worker_id=NULL, backend_name='db', last_error=COALESCE(last_error,'') || ' | recovered expired lease'
  WHERE status='running' AND lease_until IS NOT NULL AND lease_until < now()
  RETURNING queue_item_id
), candidate AS (
  SELECT qi.queue_item_id
  FROM queue_items qi
  WHERE qi.status = 'queued'
    AND qi.available_at <= now()
    AND (qi.lease_until IS NULL OR qi.lease_until < now())
  ORDER BY qi.priority ASC, qi.created_at ASC
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
UPDATE queue_items qi
SET status='running', worker_id=%(worker_id)s, lease_until=now() + (%(lease_seconds)s || ' seconds')::interval, claimed_at=now(), started_at=COALESCE(qi.started_at, now()), backend_name='db', updated_at=now()
FROM candidate c WHERE qi.queue_item_id = c.queue_item_id
RETURNING qi.queue_item_id::text, qi.job_id::text, qi.tenant_id, qi.payload, qi.retry_count, qi.max_retries, qi.priority, qi.queue_name, qi.available_at, qi.backend_name;
"""

CLAIM_BY_ID_SQL = """
UPDATE queue_items
SET status='running', worker_id=%(worker_id)s, lease_until=now() + (%(lease_seconds)s || ' seconds')::interval, claimed_at=now(), started_at=COALESCE(started_at, now()), backend_name=%(backend_name)s, updated_at=now()
WHERE queue_item_id=%(queue_item_id)s
  AND status='queued'
  AND available_at <= now()
  AND (lease_until IS NULL OR lease_until < now())
RETURNING queue_item_id::text, job_id::text, tenant_id, payload, retry_count, max_retries, priority, queue_name, available_at, backend_name;
"""

RECOVER_EXPIRED_SQL = """
UPDATE queue_items
SET status='queued', lease_until=NULL, available_at=now(), updated_at=now(), claimed_at=NULL, worker_id=NULL, backend_name=%(backend_name)s, last_error=COALESCE(last_error,'') || ' | recovered expired lease'
WHERE status='running' AND lease_until IS NOT NULL AND lease_until < now()
RETURNING queue_item_id::text, job_id::text, tenant_id, payload, retry_count, max_retries, priority, queue_name, available_at, backend_name;
"""


def _safe_execute(sql: str, params=None) -> None:
    try:
        execute(sql, params)
    except Exception:
        pass


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _epoch_seconds(value: Any) -> float:
    if value is None:
        return time.time()
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    text = str(value).strip()
    if not text:
        return time.time()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return time.time()


def compute_retry_delay_seconds(retry_count: int) -> int:
    base = max(1, int(settings.retry_backoff_base_seconds))
    cap = max(base, int(settings.retry_backoff_max_seconds))
    raw = min(cap, base * (2 ** max(retry_count, 0)))
    jitter_cap = max(0, int(settings.retry_backoff_jitter_seconds))
    jitter = random.randint(0, jitter_cap) if jitter_cap else 0
    return min(cap, raw + jitter)


def record_queue_event(event_type: str, queue_item_id: str | None = None, job_id: str | None = None, tenant_id: str = 'default', worker_id: str | None = None, backend_name: str | None = None, metadata: dict[str, Any] | None = None):
    _safe_execute(
        """INSERT INTO queue_backend_events (tenant_id, queue_item_id, job_id, worker_id, backend_name, event_type, metadata_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)""",
        (tenant_id, queue_item_id, job_id, worker_id, backend_name or settings.queue_backend, event_type, json.dumps(metadata or {})),
    )


def update_worker_state(worker_id: str, status: str = 'idle', active_claims: int = 0, tenant_id: str = 'default', metadata: dict[str, Any] | None = None):
    _safe_execute(
        """INSERT INTO queue_workers (worker_id, tenant_id, backend_name, status, concurrency_limit, active_claims, metadata_json, last_heartbeat_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,now())
        ON CONFLICT (worker_id)
        DO UPDATE SET tenant_id=EXCLUDED.tenant_id,
                      backend_name=EXCLUDED.backend_name,
                      status=EXCLUDED.status,
                      concurrency_limit=EXCLUDED.concurrency_limit,
                      active_claims=EXCLUDED.active_claims,
                      metadata_json=EXCLUDED.metadata_json,
                      last_heartbeat_at=now(),
                      updated_at=now()""",
        (worker_id, tenant_id, settings.queue_backend, status, settings.worker_concurrency, active_claims, json.dumps(metadata or {})),
    )


def _claim_one_db(worker_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CLAIM_SQL, {'worker_id': worker_id, 'lease_seconds': settings.lease_seconds})
            return cur.fetchone()


def _claim_queue_item_by_id(queue_item_id: str, worker_id: str, backend_name: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CLAIM_BY_ID_SQL, {'queue_item_id': queue_item_id, 'worker_id': worker_id, 'lease_seconds': settings.lease_seconds, 'backend_name': backend_name})
            return cur.fetchone()


def _recover_expired_queue_items(backend_name: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(RECOVER_EXPIRED_SQL, {'backend_name': backend_name})
            return cur.fetchall() or []


def mark_attempt(queue_item_id: str, job_id: str, worker_id: str, status: str, error_message: str | None = None):
    execute("INSERT INTO queue_attempts (queue_item_id, job_id, worker_id, status, error_message, finished_at) VALUES (%s,%s,%s,%s,%s,now())", (queue_item_id, job_id, worker_id, status, error_message))


class BaseQueueBackend:
    name = 'db'

    def enqueue(self, item: dict[str, Any]) -> None:
        record_queue_event('enqueued', item.get('queue_item_id'), item.get('job_id'), tenant_id=item.get('tenant_id', 'default'), backend_name=self.name, metadata={'priority': item.get('priority'), 'available_at': str(item.get('available_at'))})

    def claim_batch(self, worker_id: str, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    def acknowledge_complete(self, item: dict[str, Any], result: dict[str, Any]) -> None:
        record_queue_event('completed', item.get('queue_item_id'), item.get('job_id'), tenant_id=item.get('tenant_id', 'default'), worker_id=worker_id_or_none(item), backend_name=self.name, metadata={'result_keys': sorted((result or {}).keys())})

    def schedule_retry(self, item: dict[str, Any], delay_seconds: int, error_message: str) -> None:
        record_queue_event('retry_scheduled', item.get('queue_item_id'), item.get('job_id'), tenant_id=item.get('tenant_id', 'default'), worker_id=worker_id_or_none(item), backend_name=self.name, metadata={'delay_seconds': delay_seconds, 'error_message': error_message})

    def send_dead_letter(self, item: dict[str, Any], error_message: str) -> None:
        record_queue_event('dead_lettered', item.get('queue_item_id'), item.get('job_id'), tenant_id=item.get('tenant_id', 'default'), worker_id=worker_id_or_none(item), backend_name=self.name, metadata={'error_message': error_message})

    def cancel(self, queue_item_id: str | None, job_id: str | None = None, tenant_id: str = 'default') -> None:
        record_queue_event('cancelled', queue_item_id, job_id, tenant_id=tenant_id, backend_name=self.name)

    def health(self) -> dict[str, Any]:
        return {'backend': self.name, 'available': True, 'details': 'db queue available'}


class DbQueueBackend(BaseQueueBackend):
    name = 'db'

    def claim_batch(self, worker_id: str, limit: int) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for _ in range(max(limit, 0)):
            item = _claim_one_db(worker_id)
            if not item:
                break
            record_queue_event('claimed', item.get('queue_item_id'), item.get('job_id'), tenant_id=item.get('tenant_id', 'default'), worker_id=worker_id, backend_name=self.name, metadata={'priority': item.get('priority')})
            items.append(item)
        return items


class RedisQueueBackend(BaseQueueBackend):
    name = 'redis'

    def __init__(self, client=None):
        if client is not None:
            self.client = client
        else:
            self.client = _build_redis_client()
        if self.client is None:
            raise RuntimeError('redis backend selected but redis client dependency is unavailable')

    def _ready_key(self, tenant_id: str | None = None) -> str:
        return f"{settings.queue_backend_namespace}:queue:ready"

    def _item_key(self, queue_item_id: str) -> str:
        return f"{settings.queue_backend_namespace}:queue:item:{queue_item_id}"

    def enqueue(self, item: dict[str, Any]) -> None:
        super().enqueue(item)
        queue_item_id = item.get('queue_item_id')
        if not queue_item_id:
            return
        payload = item.get('payload') or {}
        tenant_id = item.get('tenant_id', 'default')
        score = _epoch_seconds(item.get('available_at'))
        body = {
            'queue_item_id': queue_item_id,
            'job_id': item.get('job_id') or '',
            'tenant_id': tenant_id,
            'priority': item.get('priority', 5),
            'retry_count': item.get('retry_count', 0),
            'max_retries': item.get('max_retries', 3),
            'queue_name': item.get('queue_name', 'default'),
            'payload': json.dumps(payload),
            'available_at': str(item.get('available_at') or _iso_now()),
        }
        self.client.hset(self._item_key(queue_item_id), mapping=body)
        self.client.zadd(self._ready_key(tenant_id), {queue_item_id: score})

    def claim_batch(self, worker_id: str, limit: int) -> list[dict[str, Any]]:
        recovered = _recover_expired_queue_items(self.name)
        for item in recovered:
            self.enqueue(item)
        items: list[dict[str, Any]] = []
        now = time.time()
        attempts_remaining = max(limit * 3, 1)
        while len(items) < limit and attempts_remaining > 0:
            attempts_remaining -= 1
            candidate = None
            try:
                ids = self.client.zrangebyscore(self._ready_key(), min='-inf', max=now, start=0, num=1)
            except TypeError:
                ids = self.client.zrangebyscore(self._ready_key(), '-inf', now, start=0, num=1)
            if ids:
                candidate = ids[0]
            if not candidate:
                break
            removed = self.client.zrem(self._ready_key(), candidate)
            if not removed:
                continue
            item = _claim_queue_item_by_id(candidate, worker_id, self.name)
            if not item:
                self.client.delete(self._item_key(candidate))
                continue
            record_queue_event('claimed', item.get('queue_item_id'), item.get('job_id'), tenant_id=item.get('tenant_id', 'default'), worker_id=worker_id, backend_name=self.name, metadata={'priority': item.get('priority')})
            items.append(item)
        return items

    def acknowledge_complete(self, item: dict[str, Any], result: dict[str, Any]) -> None:
        super().acknowledge_complete(item, result)
        queue_item_id = item.get('queue_item_id')
        tenant_id = item.get('tenant_id', 'default')
        if queue_item_id:
            self.client.zrem(self._ready_key(), queue_item_id)
            self.client.delete(self._item_key(queue_item_id))

    def schedule_retry(self, item: dict[str, Any], delay_seconds: int, error_message: str) -> None:
        super().schedule_retry(item, delay_seconds, error_message)
        payload = dict(item)
        payload['retry_count'] = (item.get('retry_count') or 0) + 1
        payload['available_at'] = datetime.now(timezone.utc).timestamp() + delay_seconds
        self.enqueue(payload)

    def send_dead_letter(self, item: dict[str, Any], error_message: str) -> None:
        super().send_dead_letter(item, error_message)
        queue_item_id = item.get('queue_item_id')
        tenant_id = item.get('tenant_id', 'default')
        if queue_item_id:
            self.client.zrem(self._ready_key(), queue_item_id)
            self.client.delete(self._item_key(queue_item_id))

    def cancel(self, queue_item_id: str | None, job_id: str | None = None, tenant_id: str = 'default') -> None:
        super().cancel(queue_item_id, job_id=job_id, tenant_id=tenant_id)
        if queue_item_id:
            self.client.zrem(self._ready_key(), queue_item_id)
            self.client.delete(self._item_key(queue_item_id))

    def health(self) -> dict[str, Any]:
        try:
            pong = self.client.ping()
            return {'backend': self.name, 'available': bool(pong), 'details': 'redis mirror queue reachable'}
        except Exception as exc:  # pragma: no cover - live redis failure path
            return {'backend': self.name, 'available': False, 'details': str(exc)}


_backend_cache: BaseQueueBackend | None = None
_backend_selection_error: str | None = None


def _build_redis_client():  # pragma: no cover - exercised via monkeypatch in tests
    if redis_lib is None:
        return None
    return redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)


def worker_id_or_none(item: dict[str, Any]) -> str | None:
    return item.get('worker_id')


def reset_backend_cache():  # pragma: no cover - test helper
    global _backend_cache, _backend_selection_error
    _backend_cache = None
    _backend_selection_error = None


def get_queue_backend() -> BaseQueueBackend:
    global _backend_cache, _backend_selection_error
    requested = (settings.queue_backend or 'db').lower().strip()
    if _backend_cache is not None and (_backend_cache.name == requested or (requested == 'redis' and _backend_cache.name == 'db' and _backend_selection_error)):
        return _backend_cache
    if requested == 'redis':
        try:
            _backend_cache = RedisQueueBackend()
            _backend_selection_error = None
        except Exception as exc:  # pragma: no cover - optional fallback path
            logger.warning('redis backend unavailable, falling back to db queue: %s', exc)
            _backend_cache = DbQueueBackend()
            _backend_selection_error = str(exc)
    else:
        _backend_cache = DbQueueBackend()
        _backend_selection_error = None
    return _backend_cache


def describe_queue_runtime() -> dict[str, Any]:
    backend = get_queue_backend()
    return {
        'requested_queue_backend': (settings.queue_backend or 'db').lower().strip(),
        'queue_backend': backend.name,
        'worker_concurrency': settings.worker_concurrency,
        'retry_backoff_base_seconds': settings.retry_backoff_base_seconds,
        'retry_backoff_max_seconds': settings.retry_backoff_max_seconds,
        'retry_backoff_jitter_seconds': settings.retry_backoff_jitter_seconds,
        'lease_seconds': settings.lease_seconds,
        'queue_max_claim_batch': settings.queue_max_claim_batch,
        'redis_url_configured': bool(getattr(settings, 'redis_url', '')),
        'backend_health': backend.health(),
        'backend_fallback_reason': _backend_selection_error,
    }


def enqueue_queue_item(item: dict[str, Any]) -> None:
    get_queue_backend().enqueue(item)


def cancel_queue_item(queue_item_id: str | None, job_id: str | None = None, tenant_id: str = 'default') -> None:
    try:
        get_queue_backend().cancel(queue_item_id, job_id=job_id, tenant_id=tenant_id)
    except Exception:
        record_queue_event('cancelled', queue_item_id, job_id, tenant_id=tenant_id, backend_name=settings.queue_backend, metadata={'warning': 'backend cancel raised'})


def claim_batch(worker_id: str, limit: int) -> list[dict[str, Any]]:
    backend = get_queue_backend()
    items = backend.claim_batch(worker_id, min(max(limit, 0), max(settings.queue_max_claim_batch, 1)))
    update_worker_state(worker_id, status='running' if items else 'idle', active_claims=len(items), metadata={'backend': backend.name})
    return items


def complete(queue_item_id: str, job_id: str, result: dict, item: dict[str, Any] | None = None):
    execute("UPDATE queue_items SET status='completed', lease_until=NULL, updated_at=now() WHERE queue_item_id=%s", (queue_item_id,))
    execute("UPDATE jobs SET status='completed', result=%s::jsonb, completed_at=now(), updated_at=now() WHERE job_id=%s", (json.dumps(result), job_id))
    execute("INSERT INTO job_runs (job_id, status, result) VALUES (%s,'completed',%s::jsonb)", (job_id, json.dumps(result)))
    get_queue_backend().acknowledge_complete(item or {'queue_item_id': queue_item_id, 'job_id': job_id}, result)


def fail(queue_item_id: str, job_id: str, error_message: str, retry_count: int, max_retries: int, item: dict[str, Any] | None = None):
    active_item = item or {'queue_item_id': queue_item_id, 'job_id': job_id, 'retry_count': retry_count, 'max_retries': max_retries, 'tenant_id': 'default'}
    should_retry = retry_count + 1 <= max_retries
    backend = get_queue_backend()
    if should_retry:
        delay_seconds = compute_retry_delay_seconds(retry_count)
        execute(
            "UPDATE queue_items SET status='queued', retry_count=retry_count+1, next_retry_delay_seconds=%s, last_error=%s, lease_until=NULL, available_at=now() + (%s || ' seconds')::interval, updated_at=now() WHERE queue_item_id=%s",
            (delay_seconds, error_message, delay_seconds, queue_item_id),
        )
        execute("UPDATE jobs SET status='queued', retry_count=retry_count+1, last_error=%s, updated_at=now() WHERE job_id=%s", (error_message, job_id))
        backend.schedule_retry(active_item, delay_seconds, error_message)
    else:
        execute("UPDATE queue_items SET status='dead_letter', retry_count=retry_count+1, next_retry_delay_seconds=0, last_error=%s, lease_until=NULL, updated_at=now() WHERE queue_item_id=%s", (error_message, queue_item_id))
        execute("UPDATE jobs SET status='failed', retry_count=retry_count+1, last_error=%s, updated_at=now() WHERE job_id=%s", (error_message, job_id))
        execute("INSERT INTO dead_letter_items (tenant_id, job_id, queue_item_id, reason, payload) SELECT tenant_id, job_id, queue_item_id, %s, payload FROM queue_items WHERE queue_item_id=%s", (error_message, queue_item_id))
        backend.send_dead_letter(active_item, error_message)
    execute("INSERT INTO job_runs (job_id, status, error_message) VALUES (%s,%s,%s)", (job_id, 'failed' if not should_retry else 'retrying', error_message))


def process(item: dict):
    payload = item.get('payload') or {}
    if payload.get('cancel_requested'):
        return {'cancelled': True}
    job_type = payload.get('job_type') or payload.get('type')
    if job_type == 'deliver_reminder':
        reminder_id = payload.get('reminder_id')
        row = fetch_one("SELECT reminder_id::text, task_text, due_at, status FROM reminders WHERE reminder_id = %s", (reminder_id,))
        if not row:
            raise RuntimeError(f'Reminder {reminder_id} not found')
        execute("UPDATE reminders SET status='delivered', updated_at=now() WHERE reminder_id=%s", (reminder_id,))
        return {'delivered': True, 'reminder_id': reminder_id}
    if job_type == 'research_embedding':
        return {'processed': True, 'job_type': 'research_embedding'}
    if job_type == 'social_publish':
        post_id = payload.get('post_id')
        execute("UPDATE social_posts SET status='published', published_at=now(), updated_at=now() WHERE social_post_id=%s", (post_id,))
        return {'published': True, 'post_id': post_id}
    if job_type == 'publication_bundle':
        bundle_id = payload.get('publication_bundle_id')
        execute("UPDATE publication_bundles SET status='ready', updated_at=now() WHERE publication_bundle_id=%s", (bundle_id,))
        return {'publication_bundle_ready': True, 'publication_bundle_id': bundle_id}
    return {'processed': True, 'job_type': job_type or 'generic'}


def _process_claimed_item(item: dict[str, Any], worker_id: str):
    try:
        result = process(item)
        mark_attempt(item['queue_item_id'], item['job_id'], worker_id, 'completed')
        complete(item['queue_item_id'], item['job_id'], result, item=item)
    except Exception as exc:
        mark_attempt(item['queue_item_id'], item['job_id'], worker_id, 'failed', str(exc))
        fail(item['queue_item_id'], item['job_id'], str(exc), item['retry_count'], item['max_retries'], item=item)


def run_forever():
    print(f'worker starting: {settings.worker_id}')
    concurrency = max(1, int(settings.worker_concurrency))
    update_worker_state(settings.worker_id, status='starting', active_claims=0, metadata={'backend': settings.queue_backend})
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        in_flight = set()
        while True:
            done = {future for future in in_flight if future.done()}
            if done:
                for future in done:
                    try:
                        future.result()
                    except Exception as exc:  # pragma: no cover - defensive worker guard
                        logger.exception('worker future failed: %s', exc)
                in_flight -= done
            capacity = concurrency - len(in_flight)
            if capacity > 0:
                items = claim_batch(settings.worker_id, capacity)
                for item in items:
                    in_flight.add(pool.submit(_process_claimed_item, item, settings.worker_id))
            update_worker_state(settings.worker_id, status='running' if in_flight else 'idle', active_claims=len(in_flight), metadata={'backend': settings.queue_backend})
            if not in_flight:
                time.sleep(settings.queue_poll_seconds)
            else:
                wait(in_flight, timeout=max(1, settings.queue_poll_seconds), return_when=FIRST_COMPLETED)


if __name__ == '__main__':
    run_forever()
