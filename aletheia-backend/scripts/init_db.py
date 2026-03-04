"""初始化脚本"""

import asyncio
from sqlalchemy import text
from core.database import engine, init_db
from utils.logging import logger


async def initialize_database():
    """初始化数据库"""
    logger.info("🔧 Initializing database...")

    # 创建所有表
    await init_db()

    logger.info("✅ Database initialized successfully")


async def check_connection():
    """检查数据库连接"""
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        logger.info(f"✅ Database connection OK: {result.scalar()}")


if __name__ == "__main__":
    asyncio.run(check_connection())
    asyncio.run(initialize_database())
