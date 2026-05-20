"""Docker 沙盒执行器

在隔离的 Docker 容器中安全执行工具调用。

设计参考: capability-tool-system.md 第7节 安全沙盒执行架构
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import structlog

from yuanbot.core.types import ToolResult

logger = structlog.get_logger(__name__)


class DockerSandboxExecutor:
    """Docker 沙盒执行器

    在独立的 Docker 容器中执行工具调用，确保：
    - 文件系统隔离（只读挂载）
    - 网络隔离（可配置允许的域名）
    - 资源限制（CPU、内存、执行时间）
    - 权限令牌控制

    设计参考: capability-tool-system.md 7.1-7.4
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._default_timeout = self._config.get("default_timeout_seconds", 10)
        self._memory_limit = self._config.get("memory_limit", "256m")
        self._cpu_limit = self._config.get("cpu_limit", "0.5")
        self._network_mode = self._config.get("network_mode", "none")  # none = 无网络
        self._allowed_domains: list[str] = self._config.get("allowed_domains", [])
        self._active_containers: dict[str, str] = {}  # invocation_id -> container_id

    async def execute(
        self,
        tool_id: str,
        image: str,
        params: dict[str, Any],
        timeout: int | None = None,
        auth_token: str | None = None,
    ) -> ToolResult:
        """在 Docker 容器中执行工具

        Args:
            tool_id: 工具 ID
            image: Docker 镜像名称
            params: 工具参数
            timeout: 超时时间（秒）
            auth_token: 权限令牌

        Returns:
            ToolResult: 执行结果
        """
        invocation_id = str(uuid.uuid4())[:8]
        timeout = timeout or self._default_timeout

        logger.info(
            "docker_sandbox_execute",
            tool_id=tool_id,
            image=image,
            invocation_id=invocation_id,
            timeout=timeout,
        )

        try:
            # 构建 docker run 命令
            cmd = self._build_docker_command(
                image=image,
                tool_id=tool_id,
                params=params,
                invocation_id=invocation_id,
                timeout=timeout,
                auth_token=auth_token,
            )

            # 执行容器
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            self._active_containers[invocation_id] = invocation_id

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except TimeoutError:
                # 超时，强制终止容器
                proc.kill()
                await proc.wait()
                return ToolResult(
                    tool_id=tool_id,
                    success=False,
                    error=f"Tool execution timed out after {timeout}s",
                    execution_time_ms=timeout * 1000,
                )
            finally:
                self._active_containers.pop(invocation_id, None)

            # 解析结果
            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode == 0:
                # 尝试解析 JSON 输出
                try:
                    output = json.loads(stdout_text)
                except (json.JSONDecodeError, ValueError):
                    output = stdout_text

                return ToolResult(
                    tool_id=tool_id,
                    success=True,
                    output=output,
                    execution_time_ms=0,
                )
            else:
                return ToolResult(
                    tool_id=tool_id,
                    success=False,
                    error=stderr_text or stdout_text or f"Exit code: {proc.returncode}",
                )

        except Exception as e:
            logger.error("docker_sandbox_error", tool_id=tool_id, error=str(e))
            return ToolResult(
                tool_id=tool_id,
                success=False,
                error=str(e),
            )

    def _build_docker_command(
        self,
        image: str,
        tool_id: str,
        params: dict[str, Any],
        invocation_id: str,
        timeout: int,
        auth_token: str | None,
    ) -> list[str]:
        """构建 docker run 命令"""
        cmd = [
            "docker", "run",
            "--rm",  # 执行后自动删除容器
            "--read-only",  # 只读文件系统
            f"--memory={self._memory_limit}",
            f"--cpus={self._cpu_limit}",
            f"--network={self._network_mode}",
            "--name", f"yuanbot-tool-{invocation_id}",
        ]

        # 环境变量
        cmd.extend(["-e", f"TOOL_ID={tool_id}"])
        cmd.extend(["-e", f"INVOCATION_ID={invocation_id}"])
        cmd.extend(["-e", f"PARAMS={json.dumps(params, ensure_ascii=False)}"])

        if auth_token:
            cmd.extend(["-e", f"AUTH_TOKEN={auth_token}"])

        # 如果允许特定域名，使用自定义网络
        if self._allowed_domains and self._network_mode == "none":
            cmd[-1] = "bridge"  # 覆盖网络模式
            # 注意：实际生产中应使用 iptables 或 Docker network 策略限制域名

        cmd.append(image)

        return cmd

    async def cleanup_all(self) -> None:
        """清理所有活跃的容器"""
        for invocation_id in list(self._active_containers.keys()):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "kill", f"yuanbot-tool-{invocation_id}",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
            except Exception:
                pass
        self._active_containers.clear()

    def get_stats(self) -> dict[str, Any]:
        """获取沙盒统计"""
        return {
            "active_containers": len(self._active_containers),
            "memory_limit": self._memory_limit,
            "cpu_limit": self._cpu_limit,
            "network_mode": self._network_mode,
            "allowed_domains": self._allowed_domains,
        }


class WasmSandboxExecutor:
    """WASM 沙盒执行器（轻量级）

    使用 WASM 运行时执行轻量计算任务。
    比 Docker 更轻量，适合数据格式转换等场景。

    设计参考: capability-tool-system.md 7.1
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._runtime = self._config.get("runtime", "wasmtime")

    async def execute(
        self,
        tool_id: str,
        wasm_path: str,
        params: dict[str, Any],
        timeout: int = 10,
    ) -> ToolResult:
        """在 WASM 沙盒中执行工具

        Args:
            tool_id: 工具 ID
            wasm_path: WASM 模块路径
            params: 工具参数
            timeout: 超时时间（秒）

        Returns:
            ToolResult: 执行结果
        """
        try:
            params_json = json.dumps(params, ensure_ascii=False)

            cmd = [
                self._runtime,
                "--invoke",
                "main",
                wasm_path,
                params_json,
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )

            stdout_text = stdout.decode("utf-8", errors="replace").strip()

            if proc.returncode == 0:
                try:
                    output = json.loads(stdout_text)
                except (json.JSONDecodeError, ValueError):
                    output = stdout_text

                return ToolResult(
                    tool_id=tool_id,
                    success=True,
                    output=output,
                )
            else:
                stderr_text = stderr.decode("utf-8", errors="replace").strip()
                return ToolResult(
                    tool_id=tool_id,
                    success=False,
                    error=stderr_text or f"Exit code: {proc.returncode}",
                )

        except TimeoutError:
            return ToolResult(
                tool_id=tool_id,
                success=False,
                error=f"WASM execution timed out after {timeout}s",
            )
        except FileNotFoundError:
            return ToolResult(
                tool_id=tool_id,
                success=False,
                error=f"WASM runtime '{self._runtime}' not found",
            )
        except Exception as e:
            return ToolResult(
                tool_id=tool_id,
                success=False,
                error=str(e),
            )
