from contextlib import contextmanager

try:
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except Exception:  # pragma: no cover - test fallback when psycopg isn't installed
    dict_row = None
    ConnectionPool = None

from .config import settings

pool = None


def get_pool():
    global pool
    if pool is not None:
        return pool
    if ConnectionPool is None:
        raise RuntimeError('Database driver not installed or pool not initialized')
    pool = ConnectionPool(
        conninfo=settings.database_url,
        kwargs={'row_factory': dict_row},
        min_size=1,
        max_size=10,
        open=False,
    )
    return pool


def reset_pool_for_tests():  # pragma: no cover - test helper
    global pool
    try:
        if pool is not None:
            pool.close()
    except Exception:
        pass
    pool = None


@contextmanager
def get_conn():
    pool_instance = get_pool()
    with pool_instance.connection() as conn:
        yield conn


def fetch_one(sql: str, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()


def fetch_all(sql: str, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def execute(sql: str, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
