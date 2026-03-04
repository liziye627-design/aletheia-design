"""
数据流API端点
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def get_feeds():
    """获取实时数据流"""
    return {"message": "Feeds - TODO"}


@router.post("/filter")
async def set_filter():
    """设置过滤条件"""
    return {"message": "Filter - TODO"}
