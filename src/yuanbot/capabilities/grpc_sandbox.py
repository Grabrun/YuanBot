"""gRPC 工具沙盒通信框架

提供基于 gRPC 的工具执行服务和客户端。
当 gRPC 不可用时自动 fallback 到 subprocess 执行。

设计参考: capability-tool-system.md 第7节 安全沙盒执行架构

用法::

    # Server 端
    server = create_grpc_server(port=50051)
    server.start()

    # Client 端
    client = SandboxClient("localhost:50051")
    result = await client.execute("my_tool", {"key": "value"})
    await client.close()
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ──────────────────────────────────────────────
# 可选依赖：gRPC
# ──────────────────────────────────────────────

try:
    from grpc import aio as grpc_aio

    _HAS_GRPC = True
except ImportError:
    _HAS_GRPC = False

# protobuf 生成的代码（可选）
try:
    # 当 protobuf 文件编译后可用
    # from yuanbot.capabilities.proto import tool_sandbox_pb2 as pb2
    # from yuanbot.capabilities.proto import tool_sandbox_pb2_grpc as pb2_grpc
    _HAS_PROTO = False  # 设为 True 当 proto 编译后
except ImportError:
    _HAS_PROTO = False


# ──────────────────────────────────────────────
# 数据类型
# ──────────────────────────────────────────────


class StatusCode:
    """状态码（与 proto 定义一致）"""

    OK = 0
    TOOL_NOT_FOUND = 1
    TIMEOUT = 2
    PERMISSION_DENIED = 3
    EXECUTION_ERROR = 4
    SANDBOX_ERROR = 5
    INVALID_PARAMS = 6


@dataclass
class ToolRequestData:
    """工具执行请求"""

    tool_id: str
    params_json: str = "{}"
    timeout_seconds: int = 30
    invocation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    auth_token: str = ""


@dataclass
class ToolResponseData:
    """工具执行响应"""

    invocation_id: str = ""
    success: bool = False
    output_json: str = "{}"
    error: str = ""
    execution_time_ms: int = 0
    status_code: int = StatusCode.OK


@dataclass
class ToolInfoData:
    """工具元数据"""

    tool_id: str = ""
    name: str = ""
    description: str = ""
    params_schema_json: str = "{}"
    sandbox_type: int = 0  # PROCESS=0, DOCKER=1, WASM=2, GRPC=3


# ──────────────────────────────────────────────
# 工具执行器协议
# ──────────────────────────────────────────────


class ToolExecutor:
    """工具执行器基类

    子类实现具体的工具执行逻辑。
    """

    def get_tools(self) -> list[ToolInfoData]:
        """返回可用工具列表"""
        return []

    async def execute(self, request: ToolRequestData) -> ToolResponseData:
        """执行工具

        Args:
            request: 工具执行请求

        Returns:
            ToolResponseData: 执行结果
        """
        raise NotImplementedError


# ──────────────────────────────────────────────
# gRPC Server 端实现
# ──────────────────────────────────────────────


class ToolExecutorServicer:
    """gRPC ToolExecutorService 实现

    当 gRPC 可用时作为 servicer 注册到 gRPC server。
    当 gRPC 不可用时作为独立服务使用。
    """

    def __init__(self, executor: ToolExecutor):
        self._executor = executor
        self._active_executions = 0
        self._version = "1.0.0"

    async def execute(self, request: ToolRequestData) -> ToolResponseData:
        """处理工具执行请求"""
        self._active_executions += 1
        try:
            logger.info(
                "grpc_tool_execute",
                tool_id=request.tool_id,
                invocation_id=request.invocation_id,
            )

            # 参数校验
            if not request.tool_id:
                return ToolResponseData(
                    invocation_id=request.invocation_id,
                    success=False,
                    error="tool_id is required",
                    status_code=StatusCode.INVALID_PARAMS,
                )

            # 检查工具是否存在
            available_tools = {t.tool_id for t in self._executor.get_tools()}
            if available_tools and request.tool_id not in available_tools:
                return ToolResponseData(
                    invocation_id=request.invocation_id,
                    success=False,
                    error=f"Tool not found: {request.tool_id}",
                    status_code=StatusCode.TOOL_NOT_FOUND,
                )

            # 执行
            try:
                response = await asyncio.wait_for(
                    self._executor.execute(request),
                    timeout=request.timeout_seconds,
                )
            except TimeoutError:
                return ToolResponseData(
                    invocation_id=request.invocation_id,
                    success=False,
                    error=f"Execution timed out after {request.timeout_seconds}s",
                    status_code=StatusCode.TIMEOUT,
                )

            return response

        except Exception as e:
            logger.error("grpc_servicer_error", error=str(e))
            return ToolResponseData(
                invocation_id=request.invocation_id,
                success=False,
                error=str(e),
                status_code=StatusCode.SANDBOX_ERROR,
            )
        finally:
            self._active_executions -= 1

    async def list_tools(self) -> list[ToolInfoData]:
        """返回可用工具列表"""
        return self._executor.get_tools()

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        return {
            "healthy": True,
            "version": self._version,
            "active_executions": self._active_executions,
        }


# ──────────────────────────────────────────────
# gRPC Server
# ──────────────────────────────────────────────


class GrpcToolServer:
    """gRPC 工具执行服务器

    封装 gRPC server 的创建、启动和关闭。
    当 grpc 库不可用时，所有操作变为 no-op。
    """

    def __init__(
        self,
        executor: ToolExecutor,
        host: str = "0.0.0.0",
        port: int = 50051,
    ):
        self._servicer = ToolExecutorServicer(executor)
        self._host = host
        self._port = port
        self._server: Any = None

    @property
    def is_available(self) -> bool:
        """gRPC 是否可用"""
        return _HAS_GRPC

    async def start(self) -> None:
        """启动 gRPC server"""
        if not _HAS_GRPC:
            logger.warning("grpc_not_available_server_skipped")
            return

        self._server = grpc_aio.server()
        # 注册 servicer（当 proto 编译后启用）
        # pb2_grpc.add_ToolExecutorServiceServicer_to_server(
        #     self._servicer, self._server
        # )
        address = f"{self._host}:{self._port}"
        self._server.add_insecure_port(address)
        await self._server.start()
        logger.info("grpc_server_started", address=address)

    async def stop(self, grace: float = 5.0) -> None:
        """停止 gRPC server"""
        if self._server:
            await self._server.stop(grace)
            logger.info("grpc_server_stopped")

    async def wait_for_termination(self) -> None:
        """等待 server 终止"""
        if self._server:
            await self._server.wait_for_termination()


def create_grpc_server(
    executor: ToolExecutor,
    host: str = "0.0.0.0",
    port: int = 50051,
) -> GrpcToolServer:
    """创建 gRPC 工具执行服务器

    Args:
        executor: 工具执行器实例
        host: 监听地址
        port: 监听端口

    Returns:
        GrpcToolServer 实例
    """
    return GrpcToolServer(executor=executor, host=host, port=port)


# ──────────────────────────────────────────────
# gRPC Client
# ──────────────────────────────────────────────


class SandboxClient:
    """工具沙盒客户端

    连接到 gRPC 工具执行服务器，发送工具执行请求。
    当 gRPC 不可用时自动 fallback 到 subprocess 执行。

    用法::

        client = SandboxClient("localhost:50051")
        result = await client.execute("echo", {"message": "hello"})
        await client.close()
    """

    def __init__(
        self,
        target: str = "localhost:50051",
        timeout: int = 30,
        fallback_to_subprocess: bool = True,
    ):
        self._target = target
        self._timeout = timeout
        self._fallback_to_subprocess = fallback_to_subprocess
        self._channel: Any = None
        self._connected = False

    @property
    def is_grpc_available(self) -> bool:
        """gRPC 是否可用"""
        return _HAS_GRPC

    async def connect(self) -> None:
        """建立 gRPC 连接"""
        if not _HAS_GRPC:
            logger.info("grpc_not_available_client_skipped")
            return

        try:
            self._channel = grpc_aio.insecure_channel(self._target)
            # 等待连接就绪
            await asyncio.wait_for(
                self._channel.channel_ready(),
                timeout=5,
            )
            self._connected = True
            logger.info("sandbox_client_connected", target=self._target)
        except Exception as e:
            logger.warning(
                "sandbox_client_connect_failed",
                target=self._target,
                error=str(e),
            )
            self._connected = False

    async def execute(
        self,
        tool_id: str,
        params: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> ToolResponseData:
        """执行工具

        当 gRPC 不可用或连接失败时，fallback 到 subprocess。

        Args:
            tool_id: 工具标识
            params: 工具参数
            timeout: 超时时间（秒）

        Returns:
            ToolResponseData: 执行结果
        """
        request = ToolRequestData(
            tool_id=tool_id,
            params_json=json.dumps(params or {}, ensure_ascii=False),
            timeout_seconds=timeout or self._timeout,
        )

        # 尝试 gRPC 调用
        if _HAS_GRPC and self._connected and self._channel:
            try:
                return await self._grpc_execute(request)
            except Exception as e:
                logger.warning(
                    "sandbox_grpc_execute_failed",
                    tool_id=tool_id,
                    error=str(e),
                )
                if not self._fallback_to_subprocess:
                    return ToolResponseData(
                        invocation_id=request.invocation_id,
                        success=False,
                        error=f"gRPC execution failed: {e}",
                        status_code=StatusCode.SANDBOX_ERROR,
                    )

        # Fallback: subprocess 执行
        if self._fallback_to_subprocess:
            return await self._subprocess_execute(request)

        return ToolResponseData(
            invocation_id=request.invocation_id,
            success=False,
            error="No execution method available",
            status_code=StatusCode.SANDBOX_ERROR,
        )

    async def _grpc_execute(self, request: ToolRequestData) -> ToolResponseData:
        """通过 gRPC 执行工具"""
        # 当 proto 编译后，使用 stub 调用
        # stub = pb2_grpc.ToolExecutorServiceStub(self._channel)
        # grpc_request = pb2.ToolRequest(
        #     tool_id=request.tool_id,
        #     params_json=request.params_json,
        #     timeout_seconds=request.timeout_seconds,
        #     invocation_id=request.invocation_id,
        #     auth_token=request.auth_token,
        # )
        # response = await stub.Execute(grpc_request, timeout=request.timeout_seconds)
        # return ToolResponseData(...)
        raise RuntimeError("gRPC stub not compiled yet")

    async def _subprocess_execute(self, request: ToolRequestData) -> ToolResponseData:
        """通过 subprocess 执行工具（fallback）"""
        logger.info(
            "sandbox_subprocess_fallback",
            tool_id=request.tool_id,
            invocation_id=request.invocation_id,
        )

        try:
            # 尝试查找对应的命令行工具
            cmd = self._build_subprocess_command(request)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=request.timeout_seconds,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResponseData(
                    invocation_id=request.invocation_id,
                    success=False,
                    error=f"Subprocess timed out after {request.timeout_seconds}s",
                    status_code=StatusCode.TIMEOUT,
                )

            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode == 0:
                return ToolResponseData(
                    invocation_id=request.invocation_id,
                    success=True,
                    output_json=stdout_text if stdout_text else "{}",
                    status_code=StatusCode.OK,
                )
            else:
                return ToolResponseData(
                    invocation_id=request.invocation_id,
                    success=False,
                    error=stderr_text or stdout_text or f"Exit code: {proc.returncode}",
                    status_code=StatusCode.EXECUTION_ERROR,
                )

        except FileNotFoundError:
            return ToolResponseData(
                invocation_id=request.invocation_id,
                success=False,
                error=f"Tool command not found: {request.tool_id}",
                status_code=StatusCode.TOOL_NOT_FOUND,
            )
        except Exception as e:
            return ToolResponseData(
                invocation_id=request.invocation_id,
                success=False,
                error=str(e),
                status_code=StatusCode.SANDBOX_ERROR,
            )

    def _build_subprocess_command(self, request: ToolRequestData) -> list[str]:
        """构建 subprocess 命令

        默认使用 tool_id 作为命令名，params_json 作为参数。
        子类可重写此方法自定义命令构建逻辑。
        """
        params = json.loads(request.params_json) if request.params_json else {}

        cmd = [request.tool_id]
        for key, value in params.items():
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            else:
                cmd.extend([f"--{key}", str(value)])

        return cmd

    async def list_tools(self) -> list[ToolInfoData]:
        """列出可用工具"""
        if _HAS_GRPC and self._connected and self._channel:
            try:
                # stub = pb2_grpc.ToolExecutorServiceStub(self._channel)
                # response = await stub.ListTools(pb2.ListToolsRequest())
                # return [...]
                pass
            except Exception:
                pass
        return []

    async def health_check(self) -> dict[str, Any]:
        """健康检查"""
        if _HAS_GRPC and self._connected and self._channel:
            try:
                # stub = pb2_grpc.ToolExecutorServiceStub(self._channel)
                # response = await stub.HealthCheck(pb2.HealthCheckRequest())
                # return {...}
                pass
            except Exception:
                pass
        return {"healthy": False, "connected": self._connected}

    async def close(self) -> None:
        """关闭连接"""
        if self._channel:
            await self._channel.close()
            self._connected = False
            logger.info("sandbox_client_closed")


# ──────────────────────────────────────────────
# 内置工具执行器示例
# ──────────────────────────────────────────────


class SubprocessToolExecutor(ToolExecutor):
    """基于 subprocess 的工具执行器

    将工具调用映射为 subprocess 命令执行。
    """

    def __init__(self, tool_configs: dict[str, dict[str, Any]] | None = None):
        self._tool_configs = tool_configs or {}
        self._tools = self._build_tool_list()

    def _build_tool_list(self) -> list[ToolInfoData]:
        """从配置构建工具列表"""
        tools = []
        for tool_id, config in self._tool_configs.items():
            tools.append(
                ToolInfoData(
                    tool_id=tool_id,
                    name=config.get("name", tool_id),
                    description=config.get("description", ""),
                    params_schema_json=json.dumps(
                        config.get("params_schema", {}), ensure_ascii=False
                    ),
                    sandbox_type=config.get("sandbox_type", 0),
                )
            )
        return tools

    def get_tools(self) -> list[ToolInfoData]:
        return self._tools

    async def execute(self, request: ToolRequestData) -> ToolResponseData:
        """执行 subprocess 工具"""
        config = self._tool_configs.get(request.tool_id, {})
        command_template = config.get("command", request.tool_id)

        try:
            params = json.loads(request.params_json) if request.params_json else {}
        except json.JSONDecodeError:
            return ToolResponseData(
                invocation_id=request.invocation_id,
                success=False,
                error="Invalid params_json",
                status_code=StatusCode.INVALID_PARAMS,
            )

        # 构建命令
        if isinstance(command_template, str):
            cmd = command_template.format(**params) if params else command_template
            cmd_parts = cmd.split()
        elif isinstance(command_template, list):
            cmd_parts = [str(p).format(**params) for p in command_template]
        else:
            return ToolResponseData(
                invocation_id=request.invocation_id,
                success=False,
                error=f"Invalid command template for {request.tool_id}",
                status_code=StatusCode.SANDBOX_ERROR,
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=request.timeout_seconds,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResponseData(
                    invocation_id=request.invocation_id,
                    success=False,
                    error=f"Timed out after {request.timeout_seconds}s",
                    status_code=StatusCode.TIMEOUT,
                )

            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode == 0:
                return ToolResponseData(
                    invocation_id=request.invocation_id,
                    success=True,
                    output_json=json.dumps({"output": stdout_text}, ensure_ascii=False),
                    status_code=StatusCode.OK,
                )
            else:
                return ToolResponseData(
                    invocation_id=request.invocation_id,
                    success=False,
                    error=stderr_text or stdout_text,
                    status_code=StatusCode.EXECUTION_ERROR,
                )

        except Exception as e:
            return ToolResponseData(
                invocation_id=request.invocation_id,
                success=False,
                error=str(e),
                status_code=StatusCode.SANDBOX_ERROR,
            )
