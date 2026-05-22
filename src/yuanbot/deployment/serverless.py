"""YuanBot Serverless 部署

支持 AWS Lambda / 阿里云函数计算，通过 HTTP API Gateway 触发。
使用延迟初始化（lazy init）优化冷启动时间。

使用方式:
    # AWS Lambda
    from yuanbot.deployment.serverless import create_handler
    handler = create_handler("configs/serverless.yaml")

    # 或在 serverless.yml 中:
    # handler: yuanbot.deployment.serverless.aws_handler
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ServerlessHandler:
    """Serverless 函数处理器

    延迟初始化策略：首次调用时才加载配置和初始化组件，
    后续调用复用已初始化的实例，避免每次冷启动的开销。
    """

    def __init__(self, config_path: str | Path | None = None):
        self._config_path = config_path or os.environ.get(
            "YUANBOT_CONFIG_PATH", "configs/serverless.yaml"
        )
        self._app: Any = None  # FastAPI ASGI app
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """延迟初始化：首次调用时创建 FastAPI 应用"""
        if self._initialized:
            return

        import yaml

        logger.info("serverless_cold_start", config_path=str(self._config_path))

        # 加载配置
        config_file = Path(self._config_path)
        if config_file.exists():
            with open(config_file) as f:
                raw_config = yaml.safe_load(f) or {}
        else:
            raw_config = {}

        # 从环境变量覆盖关键配置
        if os.environ.get("YUANBOT_DEBUG"):
            raw_config["debug"] = os.environ["YUANBOT_DEBUG"].lower() in ("true", "1")

        # 构建 YuanBotConfig
        from yuanbot.config import YuanBotConfig

        config = YuanBotConfig(**raw_config)

        # 创建 FastAPI 应用（延迟加载所有子系统）
        from yuanbot.app import create_app

        self._app = create_app(config)
        self._initialized = True
        logger.info("serverless_initialized")

    def handle_aws_lambda(self, event: dict[str, Any], context: Any) -> dict[str, Any]:
        """AWS Lambda 入口

        适配 AWS API Gateway HTTP API (v2.0) 格式。

        Args:
            event: Lambda 事件（API Gateway 格式）
            context: Lambda 上下文

        Returns:
            API Gateway 响应格式
        """
        self._ensure_initialized()
        return self._dispatch_aws(event)

    def handle_aliyun_fc(self, event: bytes, context: Any) -> dict[str, Any]:
        """阿里云函数计算入口

        适配阿里云 HTTP 触发器格式。

        Args:
            event: 请求体（bytes）
            context: FC 上下文

        Returns:
            FC HTTP 响应格式
        """
        self._ensure_initialized()

        try:
            request_data = json.loads(event)
        except (json.JSONDecodeError, TypeError):
            request_data = {}

        return self._dispatch_aliyun(request_data, context)

    def _dispatch_aws(self, event: dict[str, Any]) -> dict[str, Any]:
        """处理 AWS API Gateway 请求"""
        import asyncio

        # 提取请求信息
        http_info = event.get("requestContext", {}).get("http", {})
        method = http_info.get("method", event.get("httpMethod", "GET")).upper()
        path = http_info.get("path", event.get("path", "/"))
        query_params = event.get("queryStringParameters") or {}
        headers = event.get("headers") or {}
        body = event.get("body")

        # 解析 body
        if body and isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = None

        # 调用 ASGI 应用
        response = asyncio.get_event_loop().run_until_complete(
            self._call_asgi(method, path, headers, query_params, body)
        )

        return {
            "statusCode": response["status"],
            "headers": {
                "content-type": "application/json",
                **response.get("headers", {}),
            },
            "body": json.dumps(response["body"], ensure_ascii=False),
        }

    def _dispatch_aliyun(
        self, request_data: dict[str, Any], context: Any
    ) -> dict[str, Any]:
        """处理阿里云函数计算请求"""
        import asyncio

        method = request_data.get("method", "GET").upper()
        path = request_data.get("path", "/")
        query_params = request_data.get("queryParameters") or {}
        headers = request_data.get("headers") or {}
        body = request_data.get("body")

        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = None

        response = asyncio.get_event_loop().run_until_complete(
            self._call_asgi(method, path, headers, query_params, body)
        )

        return {
            "statusCode": response["status"],
            "headers": {
                "content-type": "application/json",
                **response.get("headers", {}),
            },
            "body": json.dumps(response["body"], ensure_ascii=False),
        }

    async def _call_asgi(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        query_params: dict[str, str],
        body: Any,
    ) -> dict[str, Any]:
        """通过 ASGI 接口调用 FastAPI 应用"""
        from starlette.testclient import TestClient

        # 将 query_params 编码到 URL
        if query_params:
            qs = "&".join(f"{k}={v}" for k, v in query_params.items())
            path = f"{path}?{qs}"

        # 构建请求
        request_kwargs: dict[str, Any] = {
            "method": method,
            "url": path,
            "headers": headers,
        }
        if body is not None:
            request_kwargs["json"] = body

        client = TestClient(self._app)
        response = client.request(**request_kwargs)

        try:
            resp_body = response.json()
        except Exception:
            resp_body = response.text

        return {
            "status": response.status_code,
            "headers": dict(response.headers),
            "body": resp_body,
        }


# ── 全局单例（Lambda 热复用）────────────────────
_handler: ServerlessHandler | None = None


def _get_handler() -> ServerlessHandler:
    """获取或创建全局 handler 单例（利用 Lambda 容器复用）"""
    global _handler
    if _handler is None:
        _handler = ServerlessHandler()
    return _handler


def create_handler(config_path: str | Path | None = None) -> ServerlessHandler:
    """创建 ServerlessHandler 实例

    Args:
        config_path: 配置文件路径，默认读取 YUANBOT_CONFIG_PATH 环境变量

    Returns:
        ServerlessHandler 实例
    """
    global _handler
    _handler = ServerlessHandler(config_path=config_path)
    return _handler


# ── AWS Lambda 直接入口 ──────────────────────────
def aws_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda handler 函数

    直接在 Lambda 配置中使用:
        handler: yuanbot.deployment.serverless.aws_handler
    """
    return _get_handler().handle_aws_lambda(event, context)


# ── 阿里云函数计算直接入口 ──────────────────────
def aliyun_handler(event: bytes, context: Any) -> dict[str, Any]:
    """阿里云函数计算 handler 函数

    直接在 FC 配置中使用:
        handler: yuanbot.deployment.serverless.aliyun_handler
    """
    return _get_handler().handle_aliyun_fc(event, context)
