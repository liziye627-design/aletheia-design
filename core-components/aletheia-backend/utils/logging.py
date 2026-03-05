"""
日志配置模块
"""

import os
import sys
import logging
from loguru import logger
from core.config import settings


class InterceptHandler(logging.Handler):
    """拦截标准库logging,转发到loguru"""

    def emit(self, record: logging.LogRecord) -> None:
        # 获取对应的loguru level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 查找调用者
        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging():
    """配置日志系统"""

    # 移除默认handler
    logger.remove()

    # 根据配置选择格式
    if settings.LOG_FORMAT == "json":
        # JSON格式(生产环境)
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=settings.LOG_LEVEL,
            serialize=True,  # JSON序列化
        )
    else:
        # 彩色文本格式(开发环境)
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=settings.LOG_LEVEL,
            colorize=True,
        )

    # 文件日志(可选): 无写权限时降级为仅stdout，避免服务启动失败
    try:
        os.makedirs("logs", exist_ok=True)
        logger.add(
            "logs/aletheia_{time:YYYY-MM-DD}.log",
            rotation="00:00",  # 每天午夜轮转
            retention="30 days",  # 保留30天
            compression="zip",  # 压缩旧日志
            level=settings.LOG_LEVEL,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        )
    except Exception as exc:
        logger.warning(f"⚠️ File logging disabled: {exc}")

    # 拦截标准库logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # 设置第三方库的日志级别
    for logger_name in [
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "fastapi",
        "sqlalchemy",
    ]:
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = [InterceptHandler()]

    logger.info("✅ Logging configured")
