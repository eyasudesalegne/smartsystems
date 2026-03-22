import json
from .db import fetch_all, fetch_one, execute, get_conn
from .ollama import OllamaClient

ollama = OllamaClient()


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 120):
    text = (text or '').strip()
    if not text:
        return []
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def vector_enabled() -> bool:
    row = fetch_one("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector') AS enabled")
    return bool(row and row['enabled'])


def _safe_execute(sql: str, params=None):
    try:
        execute(sql, params)
    except Exception:
        return None


def ingest_paper(tenant_id: str, actor_id: str | None, source_ref: str, title: str | None, body: str, metadata: dict):
    paper = fetch_one(
        "INSERT INTO papers (tenant_id, source_ref, title, status, metadata) VALUES (%s,%s,%s,'ingested',%s::jsonb) RETURNING paper_id::text AS paper_id",
        (tenant_id, source_ref, title, json.dumps(metadata or {})),
    )
    chunks = chunk_text(body)
    vmode = vector_enabled()
    with get_conn() as conn:
        with conn.cursor() as cur:
            for idx, chunk in enumerate(chunks):
                cur.execute(
                    "INSERT INTO paper_chunks (tenant_id, paper_id, source_type, source_ref, chunk_index, title, content, token_estimate, metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING chunk_id::text AS chunk_id",
                    (tenant_id, paper['paper_id'], 'paper', source_ref, idx, title, chunk, max(1, len(chunk) // 4), json.dumps(metadata or {})),
                )
                chunk_id = cur.fetchone()['chunk_id']
                if vmode:
                    try:
                        emb = ollama.embed(chunk)
                        vec = '[' + ','.join(str(float(x)) for x in emb) + ']'
                        cur.execute(
                            "INSERT INTO research_embeddings (tenant_id, paper_id, chunk_id, embedding_model, embedding, metadata) VALUES (%s,%s,%s,%s,%s::vector,%s::jsonb)",
                            (tenant_id, paper['paper_id'], chunk_id, ollama.base, vec, json.dumps({'source_ref': source_ref})),
                        )
                    except Exception:
                        pass
        conn.commit()
    execute("INSERT INTO source_ingestions (tenant_id, actor_id, source_type, source_ref, status, metadata) VALUES (%s,%s,'paper',%s,'completed',%s::jsonb)", (tenant_id, actor_id, source_ref, json.dumps({'paper_id': paper['paper_id'], 'chunks': len(chunks), 'vector_mode': 'pgvector' if vmode else 'lexical'})))
    return paper['paper_id'], len(chunks), ('pgvector' if vmode else 'lexical')


def ingest_document(tenant_id: str, actor_id: str | None, source_ref: str, title: str | None, body: str, metadata: dict | None = None, mime_type: str | None = None, embedding_model: str | None = None):
    metadata = metadata or {}
    document = fetch_one(
        """INSERT INTO documents (tenant_id, source_ref, title, mime_type, metadata_json)
           VALUES (%s,%s,%s,%s,%s::jsonb)
           RETURNING id::text AS document_id""",
        (tenant_id, source_ref, title, mime_type, json.dumps(metadata)),
    )
    chunks = chunk_text(body)
    stored_embedding_model = None
    embedded_chunks = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for idx, chunk in enumerate(chunks):
                cur.execute(
                    """INSERT INTO document_chunks (tenant_id, document_id, chunk_index, content, metadata_json)
                       VALUES (%s,%s,%s,%s,%s::jsonb)
                       RETURNING id::text AS chunk_id""",
                    (tenant_id, document['document_id'], idx, chunk, json.dumps({'source_ref': source_ref, **metadata})),
                )
                chunk_id = cur.fetchone()['chunk_id']
                try:
                    embedding = ollama.embed(chunk, model=embedding_model)
                    stored_embedding_model = embedding_model or ollama.base
                    cur.execute(
                        """INSERT INTO embedding_versions (tenant_id, document_chunk_id, embedding_model, embedding_dimensions, embedding_metadata)
                           VALUES (%s,%s,%s,%s,%s::jsonb)""",
                        (tenant_id, chunk_id, embedding_model or 'default', len(embedding), json.dumps({'source_ref': source_ref, 'document_id': document['document_id']})),
                    )
                    embedded_chunks += 1
                except Exception:
                    pass
        conn.commit()
    _safe_execute(
        "INSERT INTO source_ingestions (tenant_id, actor_id, source_type, source_ref, status, metadata) VALUES (%s,%s,'document',%s,'completed',%s::jsonb)",
        (tenant_id, actor_id, source_ref, json.dumps({'document_id': document['document_id'], 'chunks': len(chunks), 'embedded_chunks': embedded_chunks})),
    )
    _safe_execute(
        """INSERT INTO document_ingestion_runs (tenant_id, document_id, source_ref, actor_id, chunk_count, embedding_model, status, metadata_json)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
        (tenant_id, document['document_id'], source_ref, actor_id, len(chunks), embedding_model or 'default', 'completed', json.dumps({'embedded_chunks': embedded_chunks, 'mime_type': mime_type, **metadata})),
    )
    vector_mode = 'tracked_embeddings' if embedded_chunks else 'lexical'
    return document['document_id'], len(chunks), vector_mode, (embedding_model or 'default' if embedded_chunks else None)


def rag_governance_summary(tenant_id: str = 'default'):
    summary = {'document_count': 0, 'chunk_count': 0, 'embedding_version_count': 0, 'recent_documents': [], 'latest_embedding_models': []}
    try:
        summary['document_count'] = int((fetch_one("SELECT count(*)::int AS c FROM documents WHERE tenant_id=%s", (tenant_id,)) or {'c': 0})['c'])
        summary['chunk_count'] = int((fetch_one("SELECT count(*)::int AS c FROM document_chunks WHERE tenant_id=%s", (tenant_id,)) or {'c': 0})['c'])
        summary['embedding_version_count'] = int((fetch_one("SELECT count(*)::int AS c FROM embedding_versions WHERE tenant_id=%s", (tenant_id,)) or {'c': 0})['c'])
        summary['recent_documents'] = fetch_all(
            "SELECT id::text AS document_id, source_ref, title, mime_type, created_at::text AS created_at FROM documents WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 10",
            (tenant_id,),
        ) or []
        models = fetch_all(
            "SELECT embedding_model, count(*)::int AS chunk_count FROM embedding_versions WHERE tenant_id=%s GROUP BY embedding_model ORDER BY count(*) DESC, embedding_model ASC LIMIT 10",
            (tenant_id,),
        ) or []
        summary['latest_embedding_models'] = [dict(row) for row in models]
    except Exception:
        pass
    return summary


def search_grounded(tenant_id: str, actor_id: str | None, query: str, limit: int = 5, metadata_filters: dict | None = None):
    metadata_filters = metadata_filters or {}
    vmode = vector_enabled()
    mode = 'hybrid' if vmode else 'lexical'
    vector_rows = []
    if vmode:
        try:
            emb = ollama.embed(query)
            vec = '[' + ','.join(str(float(x)) for x in emb) + ']'
            vector_rows = fetch_all(
                """SELECT 'paper_chunk'::text AS source_type, pc.chunk_id::text AS source_ref, pc.title, pc.content,
                          (1 - (re.embedding <=> %s::vector))::float AS score,
                          pc.paper_id::text AS paper_id, pc.metadata
                   FROM research_embeddings re
                   JOIN paper_chunks pc ON pc.chunk_id = re.chunk_id
                   WHERE pc.tenant_id = %s
                   ORDER BY re.embedding <=> %s::vector
                   LIMIT %s""",
                (vec, tenant_id, vec, limit),
            )
        except Exception:
            vector_rows = []
            mode = 'lexical'
    lexical_rows = fetch_all(
        """WITH note_hits AS (
              SELECT 'research_note'::text AS source_type, rn.research_note_id::text AS source_ref, rn.title, rn.body AS content,
                     ts_rank(to_tsvector('english', coalesce(rn.title,'') || ' ' || coalesce(rn.body,'')), websearch_to_tsquery('english', %(query)s)) AS score,
                     NULL::text AS paper_id, rn.metadata
              FROM research_notes rn
              WHERE rn.tenant_id = %(tenant_id)s
                AND to_tsvector('english', coalesce(rn.title,'') || ' ' || coalesce(rn.body,'')) @@ websearch_to_tsquery('english', %(query)s)
            ), chunk_hits AS (
              SELECT 'paper_chunk'::text AS source_type, pc.chunk_id::text AS source_ref, pc.title, pc.content,
                     ts_rank(to_tsvector('english', coalesce(pc.title,'') || ' ' || coalesce(pc.content,'')), websearch_to_tsquery('english', %(query)s)) AS score,
                     pc.paper_id::text AS paper_id, pc.metadata
              FROM paper_chunks pc
              WHERE pc.tenant_id = %(tenant_id)s
                AND to_tsvector('english', coalesce(pc.title,'') || ' ' || coalesce(pc.content,'')) @@ websearch_to_tsquery('english', %(query)s)
            ), document_hits AS (
              SELECT 'document_chunk'::text AS source_type, dc.id::text AS source_ref, d.title, dc.content,
                     ts_rank(to_tsvector('english', coalesce(d.title,'') || ' ' || coalesce(dc.content,'')), websearch_to_tsquery('english', %(query)s)) AS score,
                     NULL::text AS paper_id,
                     (jsonb_build_object('document_id', d.id::text, 'source_ref', d.source_ref, 'mime_type', d.mime_type) || dc.metadata_json) AS metadata
              FROM document_chunks dc
              JOIN documents d ON d.id = dc.document_id
              WHERE dc.tenant_id = %(tenant_id)s
                AND to_tsvector('english', coalesce(d.title,'') || ' ' || coalesce(dc.content,'')) @@ websearch_to_tsquery('english', %(query)s)
            )
            SELECT * FROM (
                SELECT * FROM note_hits
                UNION ALL
                SELECT * FROM chunk_hits
                UNION ALL
                SELECT * FROM document_hits
            ) t
            ORDER BY score DESC NULLS LAST, title NULLS LAST
            LIMIT %(limit)s""",
        {'tenant_id': tenant_id, 'query': query, 'limit': limit},
    )
    seen = set()
    rows = []
    for bucket in (vector_rows, lexical_rows):
        for r in bucket:
            key = (r['source_type'], r['source_ref'])
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    execute("INSERT INTO research_queries (tenant_id, actor_id, query_text, result_count, mode) VALUES (%s,%s,%s,%s,%s)", (tenant_id, actor_id, query, len(rows), mode))
    return rows, mode
