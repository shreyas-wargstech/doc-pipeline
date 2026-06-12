from shared.config import Settings


def test_index_defaults():
    s = Settings(
        DATABASE_URL="postgresql+asyncpg://x:x@localhost/x",
        S3_ACCESS_KEY="k", S3_SECRET_KEY="s", S3_BUCKET="b",
        QDRANT_URL="http://localhost:6333",
        NEO4J_URI="bolt://localhost:7687", NEO4J_USER="neo4j", NEO4J_PASSWORD="pw",
        SQS_OCR_QUEUE_URL="http://x",
    )
    assert s.sqs_index_queue_url == ""
    assert s.index_keyword_mode == "llm_with_tfidf_fallback"
    assert s.retrieval_min_results == 3
