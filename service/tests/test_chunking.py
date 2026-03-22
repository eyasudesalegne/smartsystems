from app.retrieval import chunk_text


def test_chunking_overlap():
    chunks = chunk_text('a'*2500, chunk_size=1000, overlap=100)
    assert len(chunks) >= 3
