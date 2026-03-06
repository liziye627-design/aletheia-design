from pathlib import Path

from core.sqlite_database import SQLiteDB
from utils.query_intent import extract_keyword_terms, score_keyword_relevance


def test_extract_keyword_terms_for_cjk_question_claim():
    terms = extract_keyword_terms("苏炳添退役了吗？", max_terms=20)
    assert terms
    assert "苏炳添退役了吗？".lower() in terms
    assert any(t == "苏炳添退役" for t in terms)
    assert any(t == "苏炳添" for t in terms)


def test_score_keyword_relevance_hits_cjk_entity_phrase():
    score = score_keyword_relevance(
        "苏炳添退役了吗",
        "新华社：苏炳添宣布退役，结束21年短跑生涯。",
    )
    assert score >= 0.3


def test_sqlite_search_rss_articles_supports_cjk_claim_query(tmp_path: Path):
    db_path = tmp_path / "rss_search_test.db"
    db = SQLiteDB(str(db_path))
    db.save_rss_article(
        {
            "id": "rss_1",
            "title": "苏炳添宣布退役",
            "original_url": "https://www.people.com.cn/n1/2025/1209/c1234-12345678.html",
            "canonical_url": "https://www.people.com.cn/n1/2025/1209/c1234-12345678.html",
            "published_at": "2025-12-09T00:00:00",
            "retrieved_at": "2025-12-09T00:00:00",
            "description": "36岁的苏炳添在微博宣布退役。",
            "summary": "苏炳添退役",
            "summary_level": "fast",
            "metadata": {
                "source_id": "peoples_daily",
                "source_name": "人民日报",
                "category": "时政",
            },
        }
    )
    rows = db.search_rss_articles(keyword="苏炳添退役了吗？", limit=10, days=3650)
    assert rows
    assert any("苏炳添" in str(x.get("title") or "") for x in rows)

