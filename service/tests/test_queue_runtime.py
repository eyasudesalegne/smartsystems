from fastapi.testclient import TestClient

import app.main as main_mod
import app.worker as worker_mod
from app.main import app

client = TestClient(app)


def test_compute_retry_delay_seconds_respects_cap(monkeypatch):
    monkeypatch.setattr(worker_mod.settings, 'retry_backoff_base_seconds', 15)
    monkeypatch.setattr(worker_mod.settings, 'retry_backoff_max_seconds', 60)
    monkeypatch.setattr(worker_mod.settings, 'retry_backoff_jitter_seconds', 0)
    assert worker_mod.compute_retry_delay_seconds(0) == 15
    assert worker_mod.compute_retry_delay_seconds(1) == 30
    assert worker_mod.compute_retry_delay_seconds(4) == 60


def test_get_queue_backend_redis_falls_back_to_db(monkeypatch):
    worker_mod.reset_backend_cache()
    monkeypatch.setattr(worker_mod.settings, 'queue_backend', 'redis')
    monkeypatch.setattr(worker_mod, '_build_redis_client', lambda: None)
    backend = worker_mod.get_queue_backend()
    runtime = worker_mod.describe_queue_runtime()
    assert backend.name == 'db'
    assert runtime['requested_queue_backend'] == 'redis'
    assert runtime['queue_backend'] == 'db'
    assert runtime['backend_fallback_reason']
    worker_mod.reset_backend_cache()
    monkeypatch.setattr(worker_mod.settings, 'queue_backend', 'db')


def test_jobs_enqueue_mirrors_to_backend(monkeypatch):
    captured = []

    def fake_fetch_one(sql, params=None):
        if 'SELECT job_id::text AS job_id, status, retry_count, max_retries, result, last_error FROM jobs' in sql:
            return None
        if 'WITH new_job AS (' in sql:
            return {
                'job_id': 'job-1',
                'status': 'queued',
                'retry_count': 0,
                'max_retries': 3,
                'queue_item_id': 'queue-1',
                'tenant_id': 'default',
                'priority': 2,
                'available_at': '2026-03-17T10:00:00+00:00',
                'payload': {'job_type': 'connector_smoke'},
                'backend_name': 'db',
            }
        raise AssertionError(sql)

    monkeypatch.setattr(main_mod, 'fetch_one', fake_fetch_one)
    monkeypatch.setattr(main_mod, 'describe_queue_runtime', lambda: {'queue_backend': 'db'})
    monkeypatch.setattr(main_mod, 'enqueue_queue_item', lambda payload: captured.append(payload))

    resp = client.post('/jobs/enqueue', json={'tenant_id': 'default', 'actor_id': 'operator', 'job_type': 'connector_smoke', 'payload': {'job_type': 'connector_smoke'}, 'priority': 2, 'max_retries': 3})
    assert resp.status_code == 200
    assert resp.json()['job_id'] == 'job-1'
    assert captured[0]['queue_item_id'] == 'queue-1'
    assert captured[0]['priority'] == 2


def test_admin_queue_includes_runtime(monkeypatch):
    def fake_fetch_one(sql, params=None):
        if 'queue_workers' in sql:
            return {'c': 2}
        return {'c': 1}

    monkeypatch.setattr(main_mod, 'fetch_one', fake_fetch_one)
    monkeypatch.setattr(main_mod, 'describe_queue_runtime', lambda: {'queue_backend': 'db', 'requested_queue_backend': 'db', 'worker_concurrency': 4, 'retry_backoff_base_seconds': 15, 'retry_backoff_max_seconds': 120, 'retry_backoff_jitter_seconds': 0, 'lease_seconds': 180, 'queue_max_claim_batch': 16, 'redis_url_configured': True, 'backend_health': {'backend': 'db', 'available': True, 'details': 'ok'}, 'backend_fallback_reason': None})
    resp = client.get('/admin/queue')
    assert resp.status_code == 200
    payload = resp.json()['summary']
    assert payload['queue_backend'] == 'db'
    assert payload['worker_concurrency'] == 4
    assert payload['active_workers'] == 2


def test_fail_schedules_retry_with_exponential_backoff(monkeypatch):
    calls = []
    scheduled = []

    class FakeBackend:
        name = 'db'

        def schedule_retry(self, item, delay_seconds, error_message):
            scheduled.append((item, delay_seconds, error_message))

        def send_dead_letter(self, item, error_message):
            scheduled.append(('dead', item, error_message))

    monkeypatch.setattr(worker_mod, 'execute', lambda sql, params=None: calls.append((sql, params)))
    monkeypatch.setattr(worker_mod, 'get_queue_backend', lambda: FakeBackend())
    monkeypatch.setattr(worker_mod.settings, 'retry_backoff_base_seconds', 10)
    monkeypatch.setattr(worker_mod.settings, 'retry_backoff_max_seconds', 40)
    monkeypatch.setattr(worker_mod.settings, 'retry_backoff_jitter_seconds', 0)

    worker_mod.fail('queue-1', 'job-1', 'boom', retry_count=1, max_retries=3, item={'queue_item_id': 'queue-1', 'job_id': 'job-1', 'retry_count': 1, 'tenant_id': 'default'})
    assert scheduled[0][1] == 20
    assert any('next_retry_delay_seconds=%s' in sql for sql, _ in calls)
