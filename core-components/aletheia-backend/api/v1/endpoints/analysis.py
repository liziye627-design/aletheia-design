# -*- coding: utf-8 -*-
"""
Analysis API Router
分析服务 API 端点

整合了三个项目的核心功能:
1. 微博爬虫 + 水军检测
2. 新闻索引 + 搜索
3. 本地情感分析
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from loguru import logger


router = APIRouter(tags=["analysis"])


# ============== 请求/响应模型 ==============

class WeiboCommentCrawlRequest(BaseModel):
    """微博评论爬取请求"""
    weibo_id: str = Field(..., description="微博ID (bid)")
    user_id: str = Field(..., description="微博作者ID")
    max_pages: int = Field(default=10, ge=1, le=100, description="最大爬取页数")
    cookies: List[str] = Field(default=[], description="Cookie列表")


class WeiboUserCrawlRequest(BaseModel):
    """微博用户爬取请求"""
    user_ids: List[str] = Field(..., description="用户ID列表")
    cookies: List[str] = Field(default=[], description="Cookie列表")


class TextCleanRequest(BaseModel):
    """文本清洗请求"""
    texts: List[str] = Field(..., description="文本列表")
    remove_url: bool = Field(default=True, description="移除URL")
    remove_hashtag: bool = Field(default=True, description="移除话题")
    remove_mention: bool = Field(default=True, description="移除提及")
    min_length: int = Field(default=5, description="最小长度")


class NewsIndexRequest(BaseModel):
    """新闻索引请求"""
    documents: List[Dict[str, Any]] = Field(..., description="文档列表")
    index_name: str = Field(default="news", description="索引名称")


class NewsSearchRequest(BaseModel):
    """新闻搜索请求"""
    query: str = Field(..., description="搜索关键词")
    limit: int = Field(default=10, ge=1, le=100, description="返回数量")
    sort_by_time: bool = Field(default=False, description="按时间排序")


class SentimentAnalyzeRequest(BaseModel):
    """情感分析请求"""
    texts: List[str] = Field(..., description="文本列表")
    use_emoji: bool = Field(default=True, description="使用Emoji情感")


class BotDetectRequest(BaseModel):
    """水军检测请求"""
    user_id: str = Field(..., description="用户ID")
    follower_count: int = Field(default=0, description="粉丝数")
    following_count: int = Field(default=0, description="关注数")
    post_count: int = Field(default=0, description="发帖数")
    is_verified: bool = Field(default=False, description="是否认证")
    register_days: Optional[int] = Field(default=None, description="账号年龄(天)")


# ============== API 端点 ==============

@router.post("/weibo/comments")
async def crawl_weibo_comments(request: WeiboCommentCrawlRequest):
    """
    爬取微博评论

    - **weibo_id**: 微博ID
    - **user_id**: 作者ID
    - **max_pages**: 最大页数
    """
    try:
        from services.weibo_crawler import WeiboCommentCrawler
        from services.weibo_crawler.comment_crawler import CrawlerConfig
        import asyncio

        config = CrawlerConfig(
            max_pages=request.max_pages,
            cookies=request.cookies,
        )

        async def crawl():
            async with WeiboCommentCrawler(config) as crawler:
                comments = await crawler.crawl_comments(
                    request.weibo_id,
                    request.user_id
                )
                return crawler.to_dict_list(comments)

        results = asyncio.run(crawl())

        return {
            "success": True,
            "weibo_id": request.weibo_id,
            "total_comments": len(results),
            "comments": results[:50],  # 限制返回数量
        }

    except Exception as e:
        logger.error(f"Crawl weibo comments error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/weibo/users")
async def crawl_weibo_users(request: WeiboUserCrawlRequest):
    """
    爬取微博用户信息

    用于水军检测特征提取
    """
    try:
        from services.weibo_crawler import WeiboUserCrawler
        import asyncio

        async def crawl():
            async with WeiboUserCrawler(cookies=request.cookies) as crawler:
                users = await crawler.crawl_users_batch(request.user_ids)
                return {uid: crawler.to_dict(u) for uid, u in users.items()}

        results = asyncio.run(crawl())

        return {
            "success": True,
            "total_users": len(results),
            "users": results,
        }

    except Exception as e:
        logger.error(f"Crawl weibo users error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/text/clean")
async def clean_text(request: TextCleanRequest):
    """
    清洗文本

    移除URL、话题、提及等
    """
    try:
        from services.weibo_crawler import WeiboDataCleaner

        cleaner = WeiboDataCleaner()
        results = cleaner.batch_clean(
            request.texts,
            remove_url=request.remove_url,
            remove_hashtag=request.remove_hashtag,
            remove_mention=request.remove_mention,
            min_length=request.min_length,
        )

        return {
            "success": True,
            "total": len(results),
            "cleaned_texts": results,
        }

    except Exception as e:
        logger.error(f"Clean text error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/news/index")
async def build_news_index(request: NewsIndexRequest):
    """
    构建新闻索引

    基于TF-IDF构建倒排索引
    """
    try:
        from services.news_indexer import InverseIndexBuilder
        from pathlib import Path

        # 使用绝对路径
        index_path = Path("data/index") / request.index_name
        index_path.mkdir(parents=True, exist_ok=True)

        builder = InverseIndexBuilder(index_dir=str(index_path))
        builder.build_index(request.documents)
        builder.save_index()

        stats = builder.get_stats()

        return {
            "success": True,
            "index_name": request.index_name,
            "stats": {
                "total_docs": stats.total_docs,
                "total_terms": stats.total_terms,
                "avg_doc_length": round(stats.avg_doc_length, 2),
            },
        }

    except Exception as e:
        logger.error(f"Build news index error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/news/search")
async def search_news(request: NewsSearchRequest):
    """
    搜索新闻

    基于倒排索引的全文检索
    """
    try:
        from services.news_indexer import NewsSearcher

        searcher = NewsSearcher(index_dir="data/index/news")
        results = searcher.search(
            request.query,
            limit=request.limit,
            sort_by_time=request.sort_by_time,
        )

        return {
            "success": True,
            "query": request.query,
            "total": len(results),
            "results": [
                {
                    "doc_id": r.doc_id,
                    "score": round(r.score, 4),
                    "title": r.title,
                    "snippet": r.snippet[:200] if r.snippet else "",
                    "url": r.url,
                }
                for r in results
            ],
        }

    except Exception as e:
        logger.error(f"Search news error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sentiment/analyze")
async def analyze_sentiment(request: SentimentAnalyzeRequest):
    """
    情感分析

    本地情感分析，支持Emoji情感融合
    """
    try:
        from services.sentiment_local import LocalSentimentAnalyzer

        analyzer = LocalSentimentAnalyzer(use_emoji=request.use_emoji)
        results = analyzer.analyze_batch(request.texts)

        distribution = analyzer.get_sentiment_distribution(results)
        avg_confidence = analyzer.get_average_confidence(results)

        return {
            "success": True,
            "total": len(results),
            "distribution": distribution,
            "average_confidence": round(avg_confidence, 4),
            "results": [
                {
                    "text": r.text[:100] + "..." if len(r.text) > 100 else r.text,
                    "sentiment": r.sentiment,
                    "confidence": round(r.confidence, 4),
                    "scores": {k: round(v, 4) for k, v in r.scores.items()},
                    "emoji_sentiment": round(r.emoji_sentiment, 4),
                }
                for r in results
            ],
        }

    except Exception as e:
        logger.error(f"Analyze sentiment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bot/detect")
async def detect_bot(request: BotDetectRequest):
    """
    水军检测

    基于多维度特征检测水军账号
    """
    try:
        from services.agent_framework.bot_detector import BotDetector, AccountProfile
        from datetime import datetime, timedelta

        detector = BotDetector()

        # 构建用户画像
        register_time = None
        if request.register_days:
            register_time = datetime.now() - timedelta(days=request.register_days)

        profile = AccountProfile(
            user_id=request.user_id,
            follower_count=request.follower_count,
            following_count=request.following_count,
            post_count=request.post_count,
            is_verified=request.is_verified,
            register_time=register_time,
        )

        result = detector.detect(profile)

        return {
            "success": True,
            "user_id": request.user_id,
            "is_suspicious": result.is_suspicious,
            "risk_score": round(result.risk_score, 4),
            "risk_level": result.risk_level,
            "scores": {
                "profile": round(result.profile_score, 4),
                "behavior": round(result.behavior_score, 4),
                "content": round(result.content_score, 4),
                "social": round(result.social_score, 4),
            },
            "detected_features": result.detected_features,
            "recommendation": result.recommendation,
        }

    except Exception as e:
        logger.error(f"Detect bot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "services": {
            "weibo_crawler": "available",
            "news_indexer": "available",
            "sentiment_local": "available",
            "bot_detector": "available",
        }
    }