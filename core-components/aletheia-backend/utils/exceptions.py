"""
Aletheia 统一错误处理模块

提供统一的异常体系、错误处理和日志记录
"""

import traceback
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from loguru import logger


class AletheiaException(Exception):
    """Aletheia 基础异常类"""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "success": False,
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            },
        }


class CrawlerException(AletheiaException):
    """爬虫相关异常"""

    def __init__(
        self,
        message: str,
        platform: Optional[str] = None,
        url: Optional[str] = None,
        error_code: str = "CRAWLER_ERROR",
        status_code: int = 503,
    ):
        details = {}
        if platform:
            details["platform"] = platform
        if url:
            details["url"] = url

        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details=details,
        )


class AnalysisException(AletheiaException):
    """分析引擎相关异常"""

    def __init__(
        self,
        message: str,
        analysis_type: Optional[str] = None,
        error_code: str = "ANALYSIS_ERROR",
        status_code: int = 500,
    ):
        details = {}
        if analysis_type:
            details["analysis_type"] = analysis_type

        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details=details,
        )


class DatabaseException(AletheiaException):
    """数据库相关异常"""

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        table: Optional[str] = None,
        error_code: str = "DATABASE_ERROR",
        status_code: int = 500,
    ):
        details = {}
        if operation:
            details["operation"] = operation
        if table:
            details["table"] = table

        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details=details,
        )


class ValidationException(AletheiaException):
    """数据验证异常"""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        error_code: str = "VALIDATION_ERROR",
        status_code: int = 422,
    ):
        details = {}
        if field:
            details["field"] = field

        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details=details,
        )


class NotFoundException(AletheiaException):
    """资源未找到异常"""

    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ):
        details = {}
        if resource_type:
            details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id

        super().__init__(
            message=message, error_code="NOT_FOUND", status_code=404, details=details
        )


class RateLimitException(AletheiaException):
    """速率限制异常"""

    def __init__(
        self,
        message: str = "请求过于频繁，请稍后再试",
        retry_after: Optional[int] = None,
    ):
        details = {}
        if retry_after:
            details["retry_after"] = retry_after

        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details=details,
        )


class ExternalServiceException(AletheiaException):
    """外部服务异常"""

    def __init__(
        self,
        message: str,
        service_name: str,
        error_code: str = "EXTERNAL_SERVICE_ERROR",
        status_code: int = 503,
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details={"service": service_name},
        )


def handle_exception(exc: Exception) -> Dict[str, Any]:
    """
    统一处理异常

    Args:
        exc: 异常对象

    Returns:
        标准化的错误响应
    """
    if isinstance(exc, AletheiaException):
        # 记录已知异常
        logger.warning(
            f"[{exc.error_code}] {exc.message}", extra={"details": exc.details}
        )
        return exc.to_dict()

    # 未知异常
    error_id = logger.exception(
        f"[UNEXPECTED_ERROR] {str(exc)}\n{traceback.format_exc()}"
    )

    return {
        "success": False,
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误",
            "details": {"error_id": error_id},
        },
    }


def raise_http_exception(exc: AletheiaException) -> None:
    """
    将 AletheiaException 转换为 FastAPI HTTPException

    Args:
        exc: Aletheia 异常
    """
    raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()["error"])


# 装饰器：自动处理异常
def handle_errors(func):
    """
    装饰器：自动捕获和处理函数中的异常

    使用示例:
        @handle_errors
        async def my_endpoint():
            # 可能抛出异常的代码
            pass
    """

    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except AletheiaException as e:
            raise_http_exception(e)
        except Exception as e:
            error_response = handle_exception(e)
            raise HTTPException(status_code=500, detail=error_response["error"])

    return wrapper


# 便捷函数
def raise_crawler_error(
    message: str, platform: Optional[str] = None, url: Optional[str] = None
) -> None:
    """抛出爬虫异常"""
    raise CrawlerException(message, platform, url)


def raise_analysis_error(message: str, analysis_type: Optional[str] = None) -> None:
    """抛出分析异常"""
    raise AnalysisException(message, analysis_type)


def raise_validation_error(message: str, field: Optional[str] = None) -> None:
    """抛出验证异常"""
    raise ValidationException(message, field)


def raise_not_found(resource_type: str, resource_id: str) -> None:
    """抛出未找到异常"""
    raise NotFoundException(
        f"{resource_type} 未找到: {resource_id}", resource_type, resource_id
    )
