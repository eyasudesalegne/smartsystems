import app.db as db


class DummyConn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self

    def execute(self, sql, params=()):
        self.last_sql = sql
        self.last_params = params

    def fetchone(self):
        return {'ok': 1}

    def fetchall(self):
        return [{'ok': 1}]

    def commit(self):
        return None


class DummyPool:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.connection_calls = 0
        self.closed = False

    def connection(self):
        self.connection_calls += 1
        return DummyConn()

    def close(self):
        self.closed = True


def test_db_pool_initializes_lazily(monkeypatch):
    db.reset_pool_for_tests()
    calls = []

    def fake_pool(*args, **kwargs):
        calls.append((args, kwargs))
        return DummyPool(*args, **kwargs)

    monkeypatch.setattr(db, 'ConnectionPool', fake_pool)
    assert calls == []
    row = db.fetch_one('SELECT 1 AS ok')
    assert row == {'ok': 1}
    assert len(calls) == 1
    assert calls[0][1]['open'] is False
    db.reset_pool_for_tests()
