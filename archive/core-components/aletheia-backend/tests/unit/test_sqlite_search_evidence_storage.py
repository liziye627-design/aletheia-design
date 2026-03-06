import sqlite3
from pathlib import Path

from core.sqlite_database import SQLiteDB


def test_sqlite_persists_search_hits_and_evidence_docs(tmp_path: Path):
    db_path = tmp_path / "search_evidence_storage.db"
    db = SQLiteDB(str(db_path))
    saved_hits = db.save_search_hits_batch(
        keyword="苏炳添退役了吗",
        run_id="run_test_1",
        hits=[
            {
                "platform": "weibo",
                "source_name": "微博",
                "source_domain": "weibo.com",
                "url": "https://weibo.com/123",
                "title": "苏炳添退役",
                "snippet": "微博热议苏炳添退役",
                "rank_position": 1,
                "discovery_mode": "search",
                "discovery_tier": "B",
                "discovery_lang": "zh",
                "discovery_pool": "evidence",
                "is_promoted": True,
                "drop_reason": "",
            },
            {
                "platform": "weibo",
                "source_name": "微博",
                "source_domain": "weibo.com",
                "url": "https://weibo.com/999",
                "title": "无关热点",
                "snippet": "无关条目",
                "rank_position": 2,
                "discovery_mode": "hot",
                "discovery_tier": "B",
                "discovery_lang": "zh",
                "discovery_pool": "evidence",
                "is_promoted": False,
                "drop_reason": "LOW_RELEVANCE",
            },
        ],
    )
    saved_docs = db.save_evidence_docs_batch(
        keyword="苏炳添退役了吗",
        run_id="run_test_1",
        docs=[
            {
                "id": "ev_1",
                "source_name": "xinhua",
                "source_platform": "xinhua",
                "source_domain": "news.cn",
                "url": "https://news.cn/sports/2025-12/09/c_123.htm",
                "title": "苏炳添宣布退役",
                "snippet": "新华社报道",
                "source_tier": 1,
                "confidence": 0.91,
                "relevance_score": 0.88,
                "keyword_match": True,
                "entity_pass": True,
                "validation_status": "reachable",
                "retrieval_mode": "live",
            }
        ],
    )
    assert saved_hits == 2
    assert saved_docs == 1

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(1) FROM search_hits WHERE run_id = ?", ("run_test_1",))
    hits_count = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(1) FROM search_hits WHERE run_id = ? AND drop_reason = ?",
        ("run_test_1", "LOW_RELEVANCE"),
    )
    dropped_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(1) FROM evidence_docs WHERE run_id = ?", ("run_test_1",))
    docs_count = cur.fetchone()[0]
    conn.close()

    assert hits_count == 2
    assert dropped_count == 1
    assert docs_count == 1
