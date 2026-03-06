"""
SQLite 数据库支持 - 低成本方案
使用 SQLite 替代 PostgreSQL，无需额外安装
"""

import os
import shutil
import sqlite3
import json
import re
import asyncio
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from core.config import settings
from utils.logging import logger
from utils.query_intent import extract_keyword_terms

# SQLite 数据库文件路径
SQLITE_DB_PATH = str(getattr(settings, "SQLITE_DB_PATH", "./aletheia.db"))


def _is_sqlite_path_writable(db_path: str) -> bool:
    path = Path(db_path).expanduser().resolve()
    parent = path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return False
    if path.exists():
        return os.access(path, os.R_OK | os.W_OK)
    return os.access(parent, os.W_OK)


def _can_open_sqlite_rw(db_path: str) -> bool:
    """Probe whether SQLite can really open path in read-write mode."""
    if not _is_sqlite_path_writable(db_path):
        return False
    try:
        conn = sqlite3.connect(db_path, timeout=2.0, isolation_level=None)
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        conn.close()
        return True
    except Exception:
        return False


def _resolve_sqlite_db_path(db_path: str) -> str:
    """
    Resolve a writable SQLite path.
    Fallback to /tmp when project path is read-only.
    """
    preferred = str(db_path or SQLITE_DB_PATH)
    if _can_open_sqlite_rw(preferred):
        return preferred

    fallback = f"/tmp/{Path(preferred).name or 'aletheia.db'}"
    try:
        if not os.path.exists(fallback) and os.path.exists(preferred):
            shutil.copy2(preferred, fallback)
        Path(fallback).parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning(f"⚠️ SQLite fallback copy failed ({preferred} -> {fallback}): {exc}")

    if _can_open_sqlite_rw(fallback):
        logger.warning(
            "⚠️ SQLite path not writable, fallback to /tmp DB: "
            f"{preferred} -> {fallback}"
        )
        return fallback

    # Keep original path so caller gets a clear sqlite exception.
    return preferred


class SQLiteDB:
    """SQLite 数据库管理器"""

    def __init__(self, db_path: str = SQLITE_DB_PATH):
        self.db_path = _resolve_sqlite_db_path(db_path)
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        # Connect with timeout for busy situations
        conn = sqlite3.connect(
            self.db_path,
            timeout=60.0,  # Busy timeout
            isolation_level=None  # Autocommit mode for PRAGMA
        )
        cursor = conn.cursor()

        # Enable WAL mode for better concurrency
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")  # 30 seconds
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache

        # 创建情报表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS intel (
                id TEXT PRIMARY KEY,
                content_text TEXT NOT NULL,
                source_platform TEXT,
                original_url TEXT,
                credibility_score REAL,
                credibility_level TEXT,
                risk_flags TEXT,
                verification_status TEXT DEFAULT 'pending',
                reasoning_chain TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建搜索索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_intel_created_at ON intel(created_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_intel_platform ON intel(source_platform)
        """)

        # 创建报告表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                summary TEXT,
                content_html TEXT,
                credibility_score REAL DEFAULT 0.0,
                status TEXT DEFAULT 'complete',
                tags TEXT,
                sources TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 兼容旧库：补齐 reports.status 列
        self._ensure_column(conn, "reports", "status", "TEXT DEFAULT 'complete'")

        # RSS 文章与评论表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rss_articles (
                id TEXT PRIMARY KEY,
                source_id TEXT,
                source_name TEXT,
                category TEXT,
                title TEXT,
                link TEXT,
                canonical_url TEXT,
                published_at TEXT,
                retrieved_at TEXT,
                description TEXT,
                fast_summary TEXT,
                deep_summary TEXT,
                summary TEXT,
                summary_level TEXT,
                score REAL,
                score_breakdown TEXT,
                comment_capability TEXT,
                comment_provider TEXT,
                comment_thread_id TEXT,
                comment_stats TEXT,
                metadata TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rss_comments (
                id TEXT PRIMARY KEY,
                article_id TEXT NOT NULL,
                parent_id TEXT,
                author_id TEXT,
                author_name TEXT,
                created_at TEXT,
                like_count INTEGER,
                reply_count INTEGER,
                content_text TEXT,
                normalized_text TEXT,
                spam_score REAL,
                spam_flags TEXT,
                cluster_id INTEGER,
                ingested_at TEXT,
                raw_payload TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rss_articles_source
            ON rss_articles(source_id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rss_articles_published
            ON rss_articles(published_at)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rss_comments_article
            ON rss_comments(article_id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rss_comments_created
            ON rss_comments(created_at)
            """
        )

        # 运行级编排记录
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS investigation_runs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_investigation_runs_created_at
            ON investigation_runs(created_at)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS evidence_cache (
                id TEXT PRIMARY KEY,
                keyword TEXT NOT NULL,
                run_id TEXT NOT NULL,
                url TEXT,
                source_name TEXT,
                source_tier INTEGER DEFAULT 3,
                confidence REAL DEFAULT 0.0,
                retrieval_mode TEXT DEFAULT 'live',
                collected_at TEXT,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_evidence_cache_keyword_created_at
            ON evidence_cache(keyword, created_at)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS search_hits (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                keyword TEXT NOT NULL,
                platform TEXT,
                source_name TEXT,
                source_domain TEXT,
                url TEXT,
                title TEXT,
                snippet TEXT,
                rank_position INTEGER DEFAULT 0,
                discovery_mode TEXT DEFAULT 'search',
                discovery_tier TEXT DEFAULT 'B',
                discovery_lang TEXT DEFAULT 'zh',
                discovery_pool TEXT DEFAULT 'evidence',
                is_promoted INTEGER DEFAULT 0,
                drop_reason TEXT DEFAULT '',
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_search_hits_run_keyword
            ON search_hits(run_id, keyword, created_at)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_search_hits_url
            ON search_hits(url)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS evidence_docs (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                keyword TEXT NOT NULL,
                evidence_id TEXT,
                source_name TEXT,
                source_platform TEXT,
                source_domain TEXT,
                url TEXT,
                title TEXT,
                snippet TEXT,
                source_tier INTEGER DEFAULT 3,
                confidence REAL DEFAULT 0.0,
                relevance_score REAL DEFAULT 0.0,
                keyword_match INTEGER DEFAULT 0,
                entity_pass INTEGER DEFAULT 0,
                validation_status TEXT DEFAULT '',
                retrieval_mode TEXT DEFAULT 'live',
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_evidence_docs_run_keyword
            ON evidence_docs(run_id, keyword, created_at)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_evidence_docs_url
            ON evidence_docs(url)
            """
        )

        # GEO / Insights tables
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS geo_scans (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_geo_scans_created_at ON geo_scans(created_at)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS geo_opportunities (
                id TEXT PRIMARY KEY,
                scan_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_geo_opportunities_scan_id ON geo_opportunities(scan_id)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS geo_contents (
                id TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_geo_contents_opportunity_id ON geo_contents(opportunity_id)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS insight_mindmaps (
                run_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS insight_common_analysis (
                run_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS insight_value_insights (
                run_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS insight_generated_articles (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_insight_generated_articles_run_id
            ON insight_generated_articles(run_id)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at)
            """
        )

        conn.commit()
        conn.close()
        logger.info(f"✅ SQLite database initialized at {self.db_path}")

    def _ensure_column(
        self, conn: sqlite3.Connection, table: str, column: str, ddl_type: str
    ):
        """为既有表补齐列（SQLite 轻量迁移）。"""
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table})")
        cols = {row[1] for row in cursor.fetchall()}
        if column in cols:
            return
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")

    def save_intel(
        self, intel_data: Dict[str, Any], reasoning_chain: Dict[str, Any]
    ) -> str:
        """保存情报分析结果"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        intel_id = intel_data.get("id", f"intel_{datetime.utcnow().timestamp()}")

        cursor.execute(
            """
            INSERT OR REPLACE INTO intel 
            (id, content_text, source_platform, original_url, credibility_score, 
             credibility_level, risk_flags, verification_status, reasoning_chain, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                intel_id,
                intel_data.get("content_text", ""),
                intel_data.get("source_platform"),
                intel_data.get("original_url"),
                intel_data.get("credibility_score", 0.0),
                intel_data.get("credibility_level", "UNCERTAIN"),
                json.dumps(intel_data.get("risk_flags", [])),
                intel_data.get("verification_status", "analyzed"),
                json.dumps(reasoning_chain, ensure_ascii=False),
                json.dumps(intel_data.get("metadata", {}), ensure_ascii=False),
                datetime.utcnow().isoformat(),
            ),
        )

        conn.commit()
        conn.close()

        logger.info(f"💾 Intel saved to SQLite: {intel_id}")
        return intel_id

    def get_intel(self, intel_id: str, raw: bool = True) -> Optional[Dict[str, Any]]:
        """获取情报详情

        Args:
            intel_id: 情报ID
            raw: 是否返回原始格式（保持 reasoning_chain 为对象而不是列表）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM intel WHERE id = ?", (intel_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            result = {}
            for i, col in enumerate(cursor.description):
                value = row[i]
                col_name = col[0]
                # 解析 JSON 字段
                if col_name in ["risk_flags", "reasoning_chain", "metadata"] and value:
                    try:
                        value = json.loads(value)
                    except:
                        pass
                result[col_name] = value

            # 只在非 raw 模式下转换 reasoning_chain
            if not raw:
                if "original_url" not in result or result["original_url"] is None:
                    result["original_url"] = ""
                if "content_type" not in result:
                    result["content_type"] = "text"
                if "reasoning_chain" not in result or result["reasoning_chain"] is None:
                    result["reasoning_chain"] = []
                elif isinstance(result["reasoning_chain"], dict):
                    # 如果是对象格式，提取步骤描述为字符串列表
                    steps = result["reasoning_chain"].get("steps", [])
                    result["reasoning_chain"] = [
                        f"{step.get('stage', '')}: {step.get('conclusion', '')}"
                        for step in steps
                    ]

            return result
        return None

    def search_intel(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索情报"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM intel 
            WHERE content_text LIKE ? 
            ORDER BY created_at DESC 
            LIMIT ?
        """,
            (f"%{keyword}%", limit),
        )

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row, cursor.description) for row in rows]

    def get_recent_intel(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的情报"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM intel 
            ORDER BY created_at DESC 
            LIMIT ?
        """,
            (limit,),
        )

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row, cursor.description) for row in rows]

    def _row_to_dict(self, row, description) -> Dict[str, Any]:
        """将数据库行转换为字典"""
        result = {}
        for i, col in enumerate(description):
            value = row[i]
            # 解析 JSON 字段
            if col[0] in ["risk_flags", "reasoning_chain", "metadata"] and value:
                try:
                    value = json.loads(value)
                except:
                    pass
            result[col[0]] = value

        # 添加缺失的默认字段
        if "original_url" not in result or result["original_url"] is None:
            result["original_url"] = ""
        if "content_type" not in result:
            result["content_type"] = "text"
        # reasoning_chain 在 IntelResponse 中应该是 List[str] 格式
        if "reasoning_chain" not in result or result["reasoning_chain"] is None:
            result["reasoning_chain"] = []
        elif isinstance(result["reasoning_chain"], dict):
            # 如果是对象格式，提取步骤描述为字符串列表
            steps = result["reasoning_chain"].get("steps", [])
            result["reasoning_chain"] = [
                f"{step.get('stage', '')}: {step.get('conclusion', '')}"
                for step in steps
            ]

        return result

    def save_report(self, report_data: Dict[str, Any]) -> str:
        """保存报告"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        report_id = report_data.get("id", f"report_{datetime.utcnow().timestamp()}")

        cursor.execute(
            """
            INSERT OR REPLACE INTO reports
            (id, title, summary, content_html, credibility_score, status, tags, sources, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                report_data.get("title", ""),
                report_data.get("summary", ""),
                report_data.get("content_html", ""),
                report_data.get("credibility_score", 0.0),
                report_data.get("status", "complete"),
                json.dumps(report_data.get("tags", []), ensure_ascii=False),
                json.dumps(report_data.get("sources", []), ensure_ascii=False),
                datetime.utcnow().isoformat(),
            ),
        )

        conn.commit()
        conn.close()
        logger.info(f"💾 Report saved to SQLite: {report_id}")
        return report_id

    def save_rss_article(self, article: Dict[str, Any]) -> str:
        """保存/更新 RSS 文章"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        article_id = article.get("id", f"rss_{datetime.utcnow().timestamp()}")
        meta = article.get("metadata") or {}

        cursor.execute(
            """
            INSERT OR REPLACE INTO rss_articles (
                id, source_id, source_name, category, title, link, canonical_url,
                published_at, retrieved_at, description, fast_summary, deep_summary,
                summary, summary_level, score, score_breakdown, comment_capability,
                comment_provider, comment_thread_id, comment_stats, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article_id,
                meta.get("source_id"),
                meta.get("source_name"),
                meta.get("category") or article.get("category"),
                article.get("title"),
                article.get("original_url") or article.get("link"),
                article.get("canonical_url"),
                article.get("published_at"),
                article.get("retrieved_at"),
                article.get("description"),
                meta.get("fast_summary"),
                meta.get("deep_summary"),
                article.get("summary"),
                article.get("summary_level"),
                article.get("score"),
                json.dumps(
                    article.get("score_breakdown")
                    or meta.get("score_breakdown")
                    or {},
                    ensure_ascii=False,
                ),
                article.get("comment_capability"),
                article.get("comment_provider"),
                article.get("comment_thread_id"),
                json.dumps(article.get("comment_stats") or {}, ensure_ascii=False),
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )

        conn.commit()
        conn.close()
        return article_id

    def save_rss_comments(self, article_id: str, comments: List[Dict[str, Any]]) -> int:
        """保存 RSS 评论列表"""
        if not comments:
            return 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        inserted = 0

        for comment in comments:
            raw_id = comment.get("comment_id") or comment.get("id") or ""
            if not raw_id:
                raw = (
                    f"{article_id}:{comment.get('author', '')}:"
                    f"{comment.get('created_at', '')}:{comment.get('content_text', '')}"
                )
                raw_id = hashlib.md5(raw.encode("utf-8")).hexdigest()
            normalized = re.sub(
                r"\s+", " ", str(comment.get("content_text") or "").strip()
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO rss_comments (
                    id, article_id, parent_id, author_id, author_name, created_at,
                    like_count, reply_count, content_text, normalized_text,
                    spam_score, spam_flags, cluster_id, ingested_at, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    raw_id,
                    article_id,
                    comment.get("parent_id"),
                    comment.get("author_id"),
                    comment.get("author"),
                    comment.get("created_at"),
                    comment.get("like_count"),
                    comment.get("reply_count"),
                    comment.get("content_text"),
                    normalized,
                    comment.get("spam_score"),
                    json.dumps(comment.get("spam_flags") or [], ensure_ascii=False),
                    comment.get("cluster_id"),
                    datetime.utcnow().isoformat(),
                    json.dumps(comment.get("raw_payload") or {}, ensure_ascii=False),
                ),
            )
            inserted += 1

        conn.commit()
        conn.close()
        return inserted

    def get_rss_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rss_articles WHERE id = ?", (article_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        result: Dict[str, Any] = {}
        for i, col in enumerate(cursor.description):
            value = row[i]
            col_name = col[0]
            if col_name in {"score_breakdown", "comment_stats", "metadata"} and value:
                try:
                    value = json.loads(value)
                except Exception:
                    pass
            result[col_name] = value
        conn.close()
        return result

    def list_rss_articles(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        source_id: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        where = []
        params: List[Any] = []
        if source_id:
            where.append("source_id = ?")
            params.append(source_id)
        if category:
            where.append("category = ?")
            params.append(category)
        where_sql = " AND ".join(where)
        if where_sql:
            where_sql = "WHERE " + where_sql
        cursor.execute(f"SELECT COUNT(1) FROM rss_articles {where_sql}", params)
        total = cursor.fetchone()[0]
        offset = max(0, page - 1) * page_size
        cursor.execute(
            f"SELECT * FROM rss_articles {where_sql} "
            "ORDER BY published_at DESC LIMIT ? OFFSET ?",
            (*params, page_size, offset),
        )
        rows = cursor.fetchall()
        items: List[Dict[str, Any]] = []
        for row in rows:
            item: Dict[str, Any] = {}
            for i, col in enumerate(cursor.description):
                value = row[i]
                col_name = col[0]
                if col_name in {"score_breakdown", "comment_stats", "metadata"} and value:
                    try:
                        value = json.loads(value)
                    except Exception:
                        pass
                item[col_name] = value
            items.append(item)
        conn.close()
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": total > page * page_size,
        }

    def search_rss_articles(
        self,
        *,
        keyword: str,
        limit: int = 50,
        source_id: Optional[str] = None,
        days: Optional[int] = 30,
    ) -> List[Dict[str, Any]]:
        """
        Search rss_articles with local index semantics.
        RSS feeds without search capability can still be queried from historical
        ingested records in SQLite.
        """
        kw = str(keyword or "").strip()
        if not kw or limit <= 0:
            return []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        terms = extract_keyword_terms(kw, max_terms=16)
        if not terms:
            terms = [kw.lower()]
        # 查询条件可更宽，评分使用较短 term 集合防止 SQL 参数膨胀。
        query_terms = list(terms[:12])
        score_terms = list(terms[:6])

        where: List[str] = []
        params: List[Any] = []

        if source_id:
            where.append("source_id = ?")
            params.append(source_id)

        if isinstance(days, int) and days > 0:
            where.append(
                "datetime(COALESCE(published_at, retrieved_at, '1970-01-01T00:00:00')) >= datetime('now', ?)"
            )
            params.append(f"-{int(days)} days")

        searchable_blob = (
            "lower("
            "coalesce(title,'') || ' ' || "
            "coalesce(description,'') || ' ' || "
            "coalesce(summary,'') || ' ' || "
            "coalesce(fast_summary,'') || ' ' || "
            "coalesce(deep_summary,'')"
            ")"
        )
        token_expr = " OR ".join([f"{searchable_blob} LIKE ?" for _ in query_terms])
        where.append(f"({token_expr})")
        params.extend([f"%{t}%" for t in query_terms])

        # Deterministic local ranking:
        # title/description/summary/deep_summary with multi-term weighting.
        score_parts: List[str] = []
        score_params: List[Any] = []
        for term in score_terms:
            like_term = f"%{str(term).lower()}%"
            score_parts.extend(
                [
                    "CASE WHEN lower(coalesce(title,'')) LIKE ? THEN 3 ELSE 0 END",
                    "CASE WHEN lower(coalesce(description,'')) LIKE ? THEN 2 ELSE 0 END",
                    "CASE WHEN lower(coalesce(summary,'')) LIKE ? THEN 2 ELSE 0 END",
                    "CASE WHEN lower(coalesce(deep_summary,'')) LIKE ? THEN 1 ELSE 0 END",
                ]
            )
            score_params.extend([like_term, like_term, like_term, like_term])
        score_sql = " + ".join(score_parts) if score_parts else "0"

        where_sql = " AND ".join(where)
        if where_sql:
            where_sql = "WHERE " + where_sql

        cursor.execute(
            f"""
            SELECT *, ({score_sql}) AS local_match_score
            FROM rss_articles
            {where_sql}
            ORDER BY local_match_score DESC,
                     datetime(COALESCE(published_at, retrieved_at, '1970-01-01T00:00:00')) DESC
            LIMIT ?
            """,
            [*score_params, *params, int(limit)],
        )
        rows = cursor.fetchall()
        items: List[Dict[str, Any]] = []
        for row in rows:
            item: Dict[str, Any] = {}
            for i, col in enumerate(cursor.description):
                value = row[i]
                col_name = col[0]
                if col_name in {"score_breakdown", "comment_stats", "metadata"} and value:
                    try:
                        value = json.loads(value)
                    except Exception:
                        pass
                item[col_name] = value
            if not isinstance(item.get("metadata"), dict):
                item["metadata"] = {}
            item["metadata"]["local_match_score"] = float(item.get("local_match_score") or 0.0)
            item["metadata"]["retrieval_mode"] = "rss_local_index"
            items.append(item)
        conn.close()
        return items

    def list_rss_comments(
        self,
        *,
        article_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(1) FROM rss_comments WHERE article_id = ?",
            (article_id,),
        )
        total = cursor.fetchone()[0]
        offset = max(0, page - 1) * page_size
        cursor.execute(
            "SELECT * FROM rss_comments WHERE article_id = ? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (article_id, page_size, offset),
        )
        rows = cursor.fetchall()
        items: List[Dict[str, Any]] = []
        for row in rows:
            item: Dict[str, Any] = {}
            for i, col in enumerate(cursor.description):
                value = row[i]
                col_name = col[0]
                if col_name in {"spam_flags", "raw_payload"} and value:
                    try:
                        value = json.loads(value)
                    except Exception:
                        pass
                item[col_name] = value
            items.append(item)
        conn.close()
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": total > page * page_size,
        }

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """获取报告详情"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        result: Dict[str, Any] = {}
        for i, col in enumerate(cursor.description):
            value = row[i]
            col_name = col[0]
            if col_name in ["tags", "sources"] and value:
                try:
                    value = json.loads(value)
                except Exception:
                    value = []
            result[col_name] = value

        return result

    def list_reports(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """获取报告列表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM reports
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )

        rows = cursor.fetchall()
        conn.close()

        results: List[Dict[str, Any]] = []
        for row in rows:
            item: Dict[str, Any] = {}
            for i, col in enumerate(cursor.description):
                value = row[i]
                col_name = col[0]
                if col_name in ["tags", "sources"] and value:
                    try:
                        value = json.loads(value)
                    except Exception:
                        value = []
                item[col_name] = value
            results.append(item)

        return results

    def count_reports(self) -> int:
        """统计报告总数"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM reports")
        total = cursor.fetchone()[0]
        conn.close()
        return int(total)

    def save_investigation_run(
        self, run_id: str, status: str, payload: Dict[str, Any]
    ) -> str:
        """保存或更新编排运行记录。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO investigation_runs
            (id, status, payload_json, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                run_id,
                status,
                json.dumps(payload, ensure_ascii=False),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        conn.close()
        return run_id

    def get_investigation_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """获取编排运行记录。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM investigation_runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None

        item: Dict[str, Any] = {}
        for i, col in enumerate(cursor.description):
            val = row[i]
            name = col[0]
            if name == "payload_json" and val:
                try:
                    val = json.loads(val)
                except Exception:
                    val = {}
            item[name] = val
        return item

    def save_evidence_cache_batch(
        self, keyword: str, run_id: str, cards: List[Dict[str, Any]]
    ) -> int:
        """批量写入证据缓存。"""
        if not cards:
            return 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        saved = 0
        for idx, card in enumerate(cards):
            if not isinstance(card, dict):
                continue
            cache_id = str(card.get("id") or f"{run_id}_{idx}")
            url = str(card.get("url") or "")
            source_name = str(card.get("source_name") or "")
            source_tier = int(card.get("source_tier") or 3)
            confidence = float(card.get("confidence") or 0.0)
            retrieval_mode = str(
                card.get("retrieval_mode")
                or ("cached_evidence" if card.get("is_cached") else "live")
            )
            collected_at = str(card.get("collected_at") or now)
            cursor.execute(
                """
                INSERT OR REPLACE INTO evidence_cache
                (id, keyword, run_id, url, source_name, source_tier, confidence, retrieval_mode, collected_at, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_id,
                    str(keyword or "").strip().lower(),
                    run_id,
                    url,
                    source_name,
                    source_tier,
                    confidence,
                    retrieval_mode,
                    collected_at,
                    json.dumps(card, ensure_ascii=False),
                    now,
                ),
            )
            saved += 1
        conn.commit()
        conn.close()
        return saved

    def save_search_hits_batch(
        self,
        *,
        keyword: str,
        run_id: str,
        hits: List[Dict[str, Any]],
    ) -> int:
        """批量写入 SearchHit（发现层记录）。"""
        if not hits:
            return 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        saved = 0
        kw_norm = str(keyword or "").strip().lower()
        for idx, hit in enumerate(hits):
            if not isinstance(hit, dict):
                continue
            url = str(hit.get("url") or "").strip()
            platform = str(hit.get("platform") or "").strip()
            hit_key = f"{run_id}|{platform}|{url}|{idx}"
            hit_id = str(hit.get("id") or hashlib.sha1(hit_key.encode("utf-8")).hexdigest())
            cursor.execute(
                """
                INSERT OR REPLACE INTO search_hits
                (id, run_id, keyword, platform, source_name, source_domain, url, title, snippet, rank_position,
                 discovery_mode, discovery_tier, discovery_lang, discovery_pool, is_promoted, drop_reason,
                 payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hit_id,
                    run_id,
                    kw_norm,
                    platform,
                    str(hit.get("source_name") or ""),
                    str(hit.get("source_domain") or ""),
                    url,
                    str(hit.get("title") or "")[:500],
                    str(hit.get("snippet") or "")[:1200],
                    int(hit.get("rank_position") or (idx + 1)),
                    str(hit.get("discovery_mode") or "search"),
                    str(hit.get("discovery_tier") or "B"),
                    str(hit.get("discovery_lang") or ""),
                    str(hit.get("discovery_pool") or "evidence"),
                    1 if bool(hit.get("is_promoted")) else 0,
                    str(hit.get("drop_reason") or ""),
                    json.dumps(hit, ensure_ascii=False),
                    now,
                ),
            )
            saved += 1
        conn.commit()
        conn.close()
        return saved

    def save_evidence_docs_batch(
        self,
        *,
        keyword: str,
        run_id: str,
        docs: List[Dict[str, Any]],
    ) -> int:
        """批量写入 EvidenceDoc（证据层记录）。"""
        if not docs:
            return 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        saved = 0
        kw_norm = str(keyword or "").strip().lower()
        for idx, doc in enumerate(docs):
            if not isinstance(doc, dict):
                continue
            evidence_id = str(doc.get("id") or "")
            url = str(doc.get("url") or "").strip()
            key = f"{run_id}|{evidence_id}|{url}|{idx}"
            row_id = str(doc.get("doc_id") or hashlib.sha1(key.encode("utf-8")).hexdigest())
            cursor.execute(
                """
                INSERT OR REPLACE INTO evidence_docs
                (id, run_id, keyword, evidence_id, source_name, source_platform, source_domain, url, title, snippet,
                 source_tier, confidence, relevance_score, keyword_match, entity_pass, validation_status,
                 retrieval_mode, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    run_id,
                    kw_norm,
                    evidence_id,
                    str(doc.get("source_name") or ""),
                    str(doc.get("source_platform") or ""),
                    str(doc.get("source_domain") or ""),
                    url,
                    str(doc.get("title") or "")[:500],
                    str(doc.get("snippet") or "")[:1600],
                    int(doc.get("source_tier") or 3),
                    float(doc.get("confidence") or 0.0),
                    float(doc.get("relevance_score") or 0.0),
                    1 if bool(doc.get("keyword_match")) else 0,
                    1 if bool(doc.get("entity_pass", True)) else 0,
                    str(doc.get("validation_status") or ""),
                    str(doc.get("retrieval_mode") or "live"),
                    json.dumps(doc, ensure_ascii=False),
                    now,
                ),
            )
            saved += 1
        conn.commit()
        conn.close()
        return saved

    def get_cached_evidence(
        self, keyword: str, max_age_hours: int = 72, limit: int = 200
    ) -> List[Dict[str, Any]]:
        """按关键词与时效读取证据缓存。"""
        kw = str(keyword or "").strip().lower()
        if not kw:
            return []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        age_expr = f"-{max(1, int(max_age_hours))} hours"
        cursor.execute(
            """
            SELECT id, run_id, payload_json, created_at
            FROM evidence_cache
            WHERE keyword = ?
              AND datetime(created_at) >= datetime('now', ?)
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (kw, age_expr, int(limit)),
        )
        rows = cursor.fetchall()
        if not rows:
            cursor.execute(
                """
                SELECT id, run_id, payload_json, created_at
                FROM evidence_cache
                WHERE keyword LIKE ?
                  AND datetime(created_at) >= datetime('now', ?)
                ORDER BY datetime(created_at) DESC
                LIMIT ?
                """,
                (f"%{kw}%", age_expr, int(limit)),
            )
            rows = cursor.fetchall()
        conn.close()

        out: List[Dict[str, Any]] = []
        for cache_id, cache_run_id, payload_json, created_at in rows:
            try:
                payload = json.loads(payload_json) if payload_json else {}
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                continue
            payload["is_cached"] = True
            payload["cache_id"] = cache_id
            payload["cache_run_id"] = cache_run_id
            payload["cache_created_at"] = created_at
            payload["retrieval_mode"] = payload.get("retrieval_mode") or "cached_evidence"
            out.append(payload)
        return out

    def get_historical_evidence(
        self,
        keyword: str,
        max_age_hours: int = 720,
        limit: int = 200,
        min_token_overlap: Optional[float] = None,
        include_no_url: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        从历史 investigation_runs 中回收证据（用于 evidence_cache 为空时的降级补证）。
        """
        kw = str(keyword or "").strip().lower()
        if not kw:
            return []

        def _tokens(text: str) -> set[str]:
            s = str(text or "").lower()
            parts = set()
            for pattern in (
                r"[A-Za-z]{2,}",
                r"[0-9]{2,}",
                r"[\u4e00-\u9fff]{2,}",
                r"[A-Za-z0-9\u4e00-\u9fff]{2,}",
            ):
                for t in re.findall(pattern, s):
                    t = t.strip().lower()
                    if len(t) >= 2:
                        parts.add(t)
            return parts

        kw_tokens = _tokens(kw)
        age_expr = f"-{max(1, int(max_age_hours))} hours"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, payload_json, created_at
            FROM investigation_runs
            WHERE datetime(created_at) >= datetime('now', ?)
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (age_expr, max(100, int(limit) * 3)),
        )
        rows = cursor.fetchall()
        conn.close()

        out: List[Dict[str, Any]] = []
        seen_url: set[str] = set()
        for run_id, payload_json, created_at in rows:
            if len(out) >= int(limit):
                break
            try:
                payload = json.loads(payload_json) if payload_json else {}
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                continue

            result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
            request_obj = (
                result.get("request")
                if isinstance(result.get("request"), dict)
                else payload.get("request")
                if isinstance(payload.get("request"), dict)
                else {}
            )
            run_kw = str(request_obj.get("keyword") or request_obj.get("claim") or "").strip().lower()
            run_tokens = _tokens(run_kw)
            token_overlap = len(kw_tokens & run_tokens) / max(1, len(kw_tokens)) if kw_tokens else 0.0
            if min_token_overlap is None:
                min_overlap = 0.25
                try:
                    from core.config import settings  # lazy import to avoid cycle risk at module import time
                    min_overlap = float(
                        getattr(settings, "INVESTIGATION_HISTORICAL_CACHE_MIN_TOKEN_OVERLAP", 0.25)
                    )
                except Exception:
                    min_overlap = 0.25
            else:
                min_overlap = float(min_token_overlap)
            min_overlap = max(0.0, min(1.0, min_overlap))

            if kw not in run_kw:
                if min_overlap <= 0.0:
                    if not (kw_tokens & run_tokens):
                        continue
                elif token_overlap < min_overlap:
                    continue

            cards = result.get("evidence_registry") if isinstance(result.get("evidence_registry"), list) else []
            for card in cards:
                if len(out) >= int(limit):
                    break
                if not isinstance(card, dict):
                    continue
                url = str(card.get("url") or "").strip()
                if not url:
                    if not include_no_url:
                        continue
                elif url in seen_url:
                    continue
                if url:
                    seen_url.add(url)
                rec = dict(card)
                rec["is_cached"] = True
                rec["cache_run_id"] = str(run_id)
                rec["cache_created_at"] = str(created_at)
                rec["retrieval_mode"] = rec.get("retrieval_mode") or "cached_evidence"
                rec["cache_origin"] = "historical_runs"
                if not rec.get("url"):
                    rec["validation_status"] = rec.get("validation_status") or "derived"
                out.append(rec)

        return out


# 全局数据库实例
_sqlite_db: Optional[SQLiteDB] = None


def get_sqlite_db() -> SQLiteDB:
    """获取 SQLite 数据库实例"""
    global _sqlite_db
    if _sqlite_db is None:
        _sqlite_db = SQLiteDB()
    return _sqlite_db


# 兼容原有数据库接口
class AsyncSessionMock:
    """模拟 AsyncSession 接口"""

    def __init__(self):
        self.db = get_sqlite_db()

    async def execute(self, query, params=None):
        """执行查询"""
        # 这里可以根据需要实现
        pass

    async def commit(self):
        """提交事务"""
        pass

    async def rollback(self):
        """回滚事务"""
        pass

    async def close(self):
        """关闭连接"""
        pass


async def get_db():
    """依赖注入: 获取数据库会话（兼容接口）"""
    return AsyncSessionMock()


async def init_db():
    """初始化数据库"""
    db = get_sqlite_db()
    logger.info(f"✅ Database initialized (SQLite at {db.db_path})")


async def close_db():
    """关闭数据库连接"""
    logger.info("✅ Database connection closed")


def check_sqlite_health() -> dict:
    """Check SQLite health status"""
    try:
        db = get_sqlite_db()
        conn = sqlite3.connect(db.db_path, timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        conn.close()
        if result[0] == "ok":
            return {"status": "healthy", "type": "sqlite", "path": db.db_path}
        return {"status": "unhealthy", "error": result[0], "type": "sqlite"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e), "type": "sqlite"}


async def check_sqlite_health_async() -> dict:
    """Async wrapper for SQLite health check"""
    return await asyncio.get_event_loop().run_in_executor(None, check_sqlite_health)
