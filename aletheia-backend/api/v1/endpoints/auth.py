"""
认证API端点
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/login")
async def login():
    """用户登录"""
    return {"message": "Login endpoint - TODO"}


@router.post("/register")
async def register():
    """用户注册"""
    return {"message": "Register endpoint - TODO"}


@router.post("/refresh")
async def refresh_token():
    """刷新Token"""
    return {"message": "Refresh endpoint - TODO"}
