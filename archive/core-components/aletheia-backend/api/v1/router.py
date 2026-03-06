"""
API路由聚合
"""

from fastapi import APIRouter
from api.v1.endpoints import (
    auth,
    intel,
    intel_enhanced,
    vision,
    reports,
    feeds,
    multiplatform,
    investigations,
    geo,
    rss_articles,
    fake_news,
    analysis,
    evidence,
)
from services.mediacrawler.api_router import router as crawler_router

api_router = APIRouter()

# 注册各模块路由
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(intel.router, prefix="/intel", tags=["Intelligence"])
api_router.include_router(
    intel_enhanced.router,
    prefix="/intel/enhanced",
    tags=["Enhanced Intelligence Analysis"],
)
api_router.include_router(vision.router, prefix="/vision", tags=["Vision Analysis"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(feeds.router, prefix="/feeds", tags=["Feeds"])
api_router.include_router(
    multiplatform.router, prefix="/multiplatform", tags=["Multi-Platform Data Sources"]
)
api_router.include_router(
    investigations.router, prefix="/investigations", tags=["Investigations"]
)
api_router.include_router(geo.router, prefix="/geo", tags=["GEO"])
api_router.include_router(rss_articles.router, prefix="/rss", tags=["RSS"])
api_router.include_router(fake_news.router, prefix="/fake-news", tags=["Fake News"])
api_router.include_router(crawler_router, prefix="/crawler", tags=["Crawler"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
api_router.include_router(evidence.router, prefix="/evidence", tags=["Evidence"])
