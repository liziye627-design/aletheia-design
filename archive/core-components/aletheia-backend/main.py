"""
Aletheia Backend - 主应用入口
"""

import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from core.config import settings

# 使用 SQLite 替代 PostgreSQL
from core.sqlite_database import init_db, close_db

# from core.database import init_db as pg_init_db, close_db as pg_close_db
from core.cache import cache
from api.v1.router import api_router
from services.external.mediacrawler_process import get_mediacrawler_process_manager
from services.rss_pipeline_runner import start_rss_pipeline_task, stop_rss_pipeline_task
from utils.logging import setup_logging, logger


# =====================
# Prometheus 指标（延迟初始化避免重复注册）
# =====================
REQUEST_COUNT = None
REQUEST_DURATION = None
PROMETHEUS_APP = None

def _init_prometheus():
    """初始化 Prometheus 指标"""
    global REQUEST_COUNT, REQUEST_DURATION, PROMETHEUS_APP
    if REQUEST_COUNT is not None:
        return  # 已初始化

    from prometheus_client import make_asgi_app, Counter, Histogram, REGISTRY

    # 检查是否已注册
    try:
        REQUEST_COUNT = Counter(
            "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
        )
        REQUEST_DURATION = Histogram(
            "http_request_duration_seconds", "HTTP request duration", ["method", "endpoint"]
        )
    except ValueError:
        # 已存在，从注册表获取
        REQUEST_COUNT = REGISTRY._names_to_collectors.get('http_requests_total')
        REQUEST_DURATION = REGISTRY._names_to_collectors.get('http_request_duration_seconds')

    PROMETHEUS_APP = make_asgi_app()


# =====================
# 生命周期管理
# =====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("🚀 Aletheia Backend Starting...")

    # 初始化数据库
    try:
        await init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.warning(f"⚠️ Database init skipped: {e}")

    # 初始化Redis（本地开发默认关闭）
    if settings.REDIS_ENABLED:
        try:
            await cache.connect()
            logger.info("✅ Redis connected")
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed (will work without cache): {e}")
            # Redis不可用时继续运行,只是没有缓存功能
    else:
        logger.info("ℹ️ Redis disabled (REDIS_ENABLED=False), running without cache")

    # Sidecar: MediaCrawler（软依赖，启动失败不阻断）
    try:
        sidecar_manager = get_mediacrawler_process_manager()
        app.state.mediacrawler_bootstrap_task = asyncio.create_task(
            sidecar_manager.ensure_started()
        )
        logger.info("ℹ️ MediaCrawler sidecar bootstrap scheduled")
    except Exception as e:
        logger.warning(f"⚠️ MediaCrawler sidecar bootstrap skipped: {e}")

    # RSS pipeline background task
    try:
        start_rss_pipeline_task(app)
    except Exception as e:
        logger.warning(f"⚠️ RSS pipeline task skipped: {e}")

    # TODO: 初始化Kafka
    # TODO: 启动Celery Worker

    logger.info(f"🎉 Aletheia Backend Started - Version {settings.APP_VERSION}")

    yield

    # 关闭时执行
    logger.info("👋 Aletheia Backend Shutting down...")

    try:
        await cache.close()
    except Exception as e:
        logger.warning(f"⚠️ Redis close skipped: {e}")

    try:
        await close_db()
    except Exception as e:
        logger.warning(f"⚠️ Database close skipped: {e}")

    try:
        sidecar_manager = get_mediacrawler_process_manager()
        stop_result = await sidecar_manager.stop()
        logger.info(
            f"ℹ️ MediaCrawler sidecar stop result: {stop_result.get('reason', 'unknown')}"
        )
    except Exception as e:
        logger.warning(f"⚠️ MediaCrawler sidecar stop skipped: {e}")

    try:
        await stop_rss_pipeline_task(app)
    except Exception as e:
        logger.warning(f"⚠️ RSS pipeline stop skipped: {e}")

    logger.info("✅ Cleanup completed")


# =====================
# 创建应用实例
# =====================
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="基于第一性原理的信息审计引擎",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# =====================
# 中间件配置
# =====================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_origin_regex=settings.BACKEND_CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gzip压缩
app.add_middleware(GZipMiddleware, minimum_size=1000)


# 请求日志和性能监控
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录所有请求"""
    global REQUEST_COUNT, REQUEST_DURATION

    # 确保 Prometheus 已初始化
    if REQUEST_COUNT is None:
        _init_prometheus()

    start_time = time.time()

    # 记录请求
    logger.info(
        f"📥 {request.method} {request.url.path}",
        extra={
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else None,
        },
    )

    # 处理请求
    try:
        response = await call_next(request)

        # 计算耗时
        duration = time.time() - start_time

        # Prometheus指标
        if REQUEST_COUNT:
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code,
            ).inc()

        if REQUEST_DURATION:
            REQUEST_DURATION.labels(
                method=request.method, endpoint=request.url.path
            ).observe(duration)

        # 记录响应
        logger.info(
            f"📤 {request.method} {request.url.path} - {response.status_code} - {duration:.3f}s",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration": duration,
            },
        )

        return response

    except Exception as e:
        duration = time.time() - start_time

        logger.error(
            f"❌ {request.method} {request.url.path} - Error: {str(e)} - {duration:.3f}s",
            exc_info=True,
            extra={
                "method": request.method,
                "path": request.url.path,
                "error": str(e),
                "duration": duration,
            },
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "detail": str(e) if settings.DEBUG else "An error occurred",
            },
        )


# =====================
# 路由注册
# =====================


# =====================
# Health Check Endpoints
# =====================

@app.get("/health", tags=["Health"])
async def health_check():
    """
    Basic health check endpoint.
    Returns overall system health status.
    """
    from utils.health import check_health
    return await check_health()


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """
    Readiness check endpoint.
    Returns whether the service is ready to accept traffic.
    Used by Kubernetes/Docker for container orchestration.
    """
    from utils.health import check_readiness
    result = await check_readiness()
    if not result.get("ready"):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=result,
        )
    return result


@app.get("/health/live", tags=["Health"])
async def liveness_check():
    """
    Liveness check endpoint.
    Returns whether the service process is alive.
    Used by Kubernetes/Docker to detect deadlocks.
    """
    from utils.health import check_liveness
    return await check_liveness()


@app.get("/health/components", tags=["Health"])
async def components_health():
    """
    Detailed component health check.
    Returns health status of all system components.
    """
    from utils.health import check_health
    return await check_health()


# Prometheus指标
if settings.PROMETHEUS_ENABLED:
    _init_prometheus()
    if PROMETHEUS_APP:
        app.mount("/metrics", PROMETHEUS_APP)


# API路由
app.include_router(api_router, prefix=settings.API_V1_STR)


# =====================
# 根端点
# =====================
@app.get("/", tags=["Root"])
async def root():
    """根端点"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "description": "Aletheia - 真相解蔽引擎后端API",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics" if settings.PROMETHEUS_ENABLED else None,
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """避免浏览器默认请求触发404日志"""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =====================
# 全局异常处理
# =====================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(
        f"Unhandled exception: {exc}",
        exc_info=True,
        extra={
            "path": request.url.path,
            "method": request.method,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred",
        },
    )


# =====================
# 初始化日志
# =====================
setup_logging()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
