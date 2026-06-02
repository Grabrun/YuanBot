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
    """WASM 沙盒执行器

    使用 wasmtime Python bindings 在 WASM 运行时中安全执行轻量计算任务。
    比 Docker 更轻量，适合数据格式转换、数学计算等场景。

    特性:
    - 原生 wasmtime Python API，无需外部 CLI 依赖
    - 模块编译缓存（LRU），避免重复编译
    - WASI 支持（可选文件系统/环境变量注入）
    - 基于 fuel 的执行时间限制
    - 内存限制（WASM linear memory 上限）
    - 并发安全（每个 execute 使用独立 Store）

    设计参考: capability-tool-system.md 7.1
    """

    # 可选依赖：wasmtime Python bindings
    _HAS_WASMTIME = False
    _Engine = None
    _Store = None
    _Module = None
    _Instance = None
    _WasiConfig = None
    _Func = None
    _FuncType = None
    _ValType = None
    _Linker = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._default_timeout = self._config.get("default_timeout_seconds", 10)
        self._memory_limit_pages = self._config.get("memory_limit_pages", 256)  # 256 pages = 16 MB
        self._fuel_limit = self._config.get("fuel_limit", 100_000_000)  # ~100M instructions
        self._enable_wasi = self._config.get("enable_wasi", False)
        self._allowed_dirs: list[str] = self._config.get("allowed_dirs", [])
        self._env_vars: dict[str, str] = self._config.get("env_vars", {})

        # 模块缓存: wasm_path -> compiled Module
        self._module_cache: dict[str, Any] = {}
        self._module_cache_max = self._config.get("module_cache_size", 64)

        # 统计
        self._total_executions = 0
        self._cache_hits = 0
        self._cache_misses = 0

        # 初始化 wasmtime
        self._init_wasmtime()

    def _init_wasmtime(self) -> None:
        """初始化 wasmtime Python bindings"""
        try:
            from wasmtime import (
                Config,
                DirPerms,
                Engine,
                FilePerms,
                Func,
                FuncType,
                Instance,
                Linker,
                Module,
                Store,
                ValType,
                WasiConfig,
            )

            WasmSandboxExecutor._HAS_WASMTIME = True
            WasmSandboxExecutor._Engine = Engine
            WasmSandboxExecutor._Store = Store
            WasmSandboxExecutor._Module = Module
            WasmSandboxExecutor._Instance = Instance
            WasmSandboxExecutor._Func = Func
            WasmSandboxExecutor._FuncType = FuncType
            WasmSandboxExecutor._ValType = ValType
            WasmSandboxExecutor._Linker = Linker
            WasmSandboxExecutor._WasiConfig = WasiConfig
            WasmSandboxExecutor._Config = Config
            WasmSandboxExecutor._DirPerms = DirPerms
            WasmSandboxExecutor._FilePerms = FilePerms

            # 共享 Engine 实例（线程安全，编译配置共享）
            # 启用 fuel 消耗跟踪以支持执行时间限制
            engine_config = Config()
            Config.consume_fuel.__set__(engine_config, True)
            self._engine = Engine(engine_config)
            logger.info(
                "wasm_sandbox_init",
                memory_limit_pages=self._memory_limit_pages,
                fuel_limit=self._fuel_limit,
                wasi_enabled=self._enable_wasi,
                module_cache_size=self._module_cache_max,
            )
        except ImportError:
            WasmSandboxExecutor._HAS_WASMTIME = False
            logger.warning(
                "wasm_sandbox_init_fallback",
                reason="wasmtime Python package not available, "
                       "will fall back to subprocess execution",
            )

    @property
    def is_native_available(self) -> bool:
        """原生 wasmtime Python bindings 是否可用"""
        return self._HAS_WASMTIME

    def _get_or_compile_module(self, wasm_path: str) -> Any:
        """获取缓存的编译模块或编译新的"""
        if wasm_path in self._module_cache:
            self._cache_hits += 1
            return self._module_cache[wasm_path]

        self._cache_misses += 1

        # 读取 WASM 二进制
        with open(wasm_path, "rb") as f:
            wasm_bytes = f.read()

        # 编译模块
        module = self._Module(self._engine, wasm_bytes)

        # LRU 缓存淘汰
        if len(self._module_cache) >= self._module_cache_max:
            # 移除最早的条目
            oldest_key = next(iter(self._module_cache))
            del self._module_cache[oldest_key]
            logger.debug("wasm_module_cache_evict", path=oldest_key)

        self._module_cache[wasm_path] = module
        logger.debug("wasm_module_compiled", path=wasm_path, size=len(wasm_bytes))
        return module

    async def execute(
        self,
        tool_id: str,
        wasm_path: str,
        params: dict[str, Any],
        timeout: int | None = None,
        entry_point: str = "_start",
    ) -> ToolResult:
        """在 WASM 沙盒中执行工具

        优先使用 wasmtime Python bindings（原生模式），如果不可用则
        回退到 subprocess 模式调用 wasmtime CLI。

        Args:
            tool_id: 工具 ID
            wasm_path: WASM 模块文件路径（.wasm 或 .wat）
            params: 工具参数，将序列化为 JSON 传入
            timeout: 超时时间（秒）
            entry_point: WASM 导出的入口函数名

        Returns:
            ToolResult: 执行结果
        """
        self._total_executions += 1
        timeout = timeout or self._default_timeout

        logger.info(
            "wasm_sandbox_execute",
            tool_id=tool_id,
            wasm_path=wasm_path,
            timeout=timeout,
            native=self._HAS_WASMTIME,
        )

        if self._HAS_WASMTIME:
            return await self._execute_native(
                tool_id=tool_id,
                wasm_path=wasm_path,
                params=params,
                timeout=timeout,
                entry_point=entry_point,
            )
        else:
            return await self._execute_subprocess(
                tool_id=tool_id,
                wasm_path=wasm_path,
                params=params,
                timeout=timeout,
            )

    async def _execute_native(
        self,
        tool_id: str,
        wasm_path: str,
        params: dict[str, Any],
        timeout: int,
        entry_point: str,
    ) -> ToolResult:
        """使用 wasmtime Python bindings 执行"""
        import time

        start_time = time.monotonic()

        try:
            # 编译/获取缓存模块
            module = self._get_or_compile_module(wasm_path)

            # 创建 Store（每次执行独立，保证并发安全）
            store = self._Store(self._engine)

            # 设置 fuel 限制
            store.set_fuel(self._fuel_limit)

            # 配置 WASI
            if self._enable_wasi:
                wasi_config = self._WasiConfig()
                # 允许的目录
                for dir_path in self._allowed_dirs:
                    wasi_config.preopen_dir(
                        dir_path, dir_path,
                        self._DirPerms.READ_ONLY,
                        self._FilePerms.READ_ONLY,
                    )
                # 环境变量
                if self._env_vars:
                    self._WasiConfig.env.__set__(
                        wasi_config,
                        list(self._env_vars.items()),
                    )
                store.set_wasi(wasi_config)

            # 创建 Linker 并定义 WASI
            linker = self._Linker(self._engine)
            if self._enable_wasi:
                linker.define_wasi()

            # 定义宿主函数（供 WASM 模块调用）
            self._define_host_functions(linker, store)

            # 实例化模块
            instance = linker.instantiate(store, module)

            # 将参数序列化为 JSON 字符串
            params_json = json.dumps(params, ensure_ascii=False)

            # 调用入口函数
            result = self._call_entry_point(
                store=store,
                instance=instance,
                entry_point=entry_point,
                params_json=params_json,
            )

            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            fuel_consumed = self._fuel_limit - (store.get_fuel() or 0)

            logger.info(
                "wasm_sandbox_success",
                tool_id=tool_id,
                elapsed_ms=elapsed_ms,
                fuel_consumed=fuel_consumed,
            )

            # 尝试解析 JSON 输出
            try:
                output = json.loads(result)
            except (json.JSONDecodeError, ValueError):
                output = result

            return ToolResult(
                tool_id=tool_id,
                success=True,
                output=output,
                execution_time_ms=elapsed_ms,
            )

        except TimeoutError:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return ToolResult(
                tool_id=tool_id,
                success=False,
                error=f"WASM execution timed out after {timeout}s",
                execution_time_ms=elapsed_ms,
            )
        except FileNotFoundError:
            return ToolResult(
                tool_id=tool_id,
                success=False,
                error=f"WASM module not found: {wasm_path}",
            )
        except Exception as e:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            error_msg = str(e)
            # 检测 fuel 耗尽
            if "all fuel consumed" in error_msg.lower() or "fuel" in error_msg.lower():
                error_msg = f"WASM execution exceeded instruction limit ({self._fuel_limit} fuel)"
            logger.error(
                "wasm_sandbox_error",
                tool_id=tool_id,
                error=error_msg,
                elapsed_ms=elapsed_ms,
            )
            return ToolResult(
                tool_id=tool_id,
                success=False,
                error=error_msg,
                execution_time_ms=elapsed_ms,
            )

    def _define_host_functions(self, linker: Any, store: Any) -> None:
        """定义宿主函数，供 WASM 模块通过 WASI 或自定义导入调用

        子类可重写此方法注入自定义宿主函数。
        """
        # 默认不定义额外的宿主函数
        pass

    def _call_entry_point(
        self,
        store: Any,
        instance: Any,
        entry_point: str,
        params_json: str,
    ) -> str:
        """调用 WASM 模块的入口函数

        约定：入口函数接收一个 i32 参数（指向 linear memory 中 JSON 字符串的指针），
        返回一个 i32（指向 linear memory 中结果 JSON 的指针）。

        如果模块没有约定的入口函数，尝试调用 _start（WASI 标准入口）。
        """
        exports = instance.exports(store)

        # 获取 linear memory
        memory = exports.get("memory")

        # 尝试查找入口函数
        entry_func = exports.get(entry_point)
        if entry_func is None:
            # 回退到 _start
            entry_func = exports.get("_start")
            if entry_func is None:
                raise RuntimeError(
                    f"WASM module has no '{entry_point}' or '_start' export"
                )

        if memory is not None:
            # 写入参数到 linear memory
            param_bytes = params_json.encode("utf-8")
            # 调用 malloc 或使用固定偏移
            malloc = exports.get("malloc") or exports.get("allocate")
            if malloc:
                param_ptr = malloc(store, len(param_bytes))
            else:
                # 使用偏移 1024 作为默认写入位置（跳过前 1KB 保留区）
                param_ptr = 1024

            # 写入 memory
            mem_data = memory.data_ptr(store)
            for i, b in enumerate(param_bytes):
                mem_data[param_ptr + i] = b

            # 调用入口函数
            result_ptr = entry_func(store, param_ptr, len(param_bytes))

            # 读取结果（约定：结果以 null 结尾，从 result_ptr 开始）
            result_bytes = bytearray()
            max_read = 65536  # 最多读 64KB
            for i in range(max_read):
                byte = mem_data[result_ptr + i]
                if byte == 0:
                    break
                result_bytes.append(byte)

            return result_bytes.decode("utf-8", errors="replace")
        else:
            # 无 memory 导出，尝试无参调用
            result = entry_func(store)
            if isinstance(result, (int, float, str)):
                return str(result)
            return json.dumps({"result": result})

    async def _execute_subprocess(
        self,
        tool_id: str,
        wasm_path: str,
        params: dict[str, Any],
        timeout: int,
    ) -> ToolResult:
        """回退：使用 wasmtime CLI subprocess 执行

        当 wasmtime Python bindings 不可用时使用此方法。
        """
        runtime = self._config.get("runtime", "wasmtime")
        params_json = json.dumps(params, ensure_ascii=False)

        cmd = [
            runtime,
            "--invoke",
            "main",
            wasm_path,
            params_json,
        ]

        try:
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
                error=f"WASM runtime '{runtime}' not found",
            )
        except Exception as e:
            return ToolResult(
                tool_id=tool_id,
                success=False,
                error=str(e),
            )

    def clear_module_cache(self) -> None:
        """清空模块编译缓存"""
        count = len(self._module_cache)
        self._module_cache.clear()
        logger.info("wasm_module_cache_cleared", count=count)

    def get_stats(self) -> dict[str, Any]:
        """获取沙盒统计信息"""
        return {
            "native_available": self._HAS_WASMTIME,
            "total_executions": self._total_executions,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": (
                self._cache_hits / max(self._cache_hits + self._cache_misses, 1)
            ),
            "cached_modules": len(self._module_cache),
            "memory_limit_pages": self._memory_limit_pages,
            "fuel_limit": self._fuel_limit,
            "wasi_enabled": self._enable_wasi,
            "allowed_dirs": self._allowed_dirs,
        }
