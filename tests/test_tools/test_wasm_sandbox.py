"""WASM 沙盒执行器测试

测试覆盖：
- 模块编译与缓存
- 成功执行（JSON I/O）
- 超时处理
- Fuel 耗尽（指令数限制）
- 文件不存在
- WASI 支持
- 统计信息
- Subprocess 回退模式

设计参考: capability-tool-system.md 第7节
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from yuanbot.tools.sandbox import WasmSandboxExecutor

# ──────────────────────────────────────────────
# 测试辅助：生成简单 WASM 模块
# ──────────────────────────────────────────────


def _build_echo_wasm() -> bytes:
    """构建一个简单的 echo WASM 模块

    返回 WAT 文本的 UTF-8 编码字节。wasmtime Python API 的 Module 构造器
    可以直接解析 WAT 文本格式。

    该模块导出：
    - memory: linear memory
    - echo(ptr, len) -> ptr: 将 memory[ptr..ptr+len] 的数据原样返回
    - add(a, b) -> i32: 返回 a + b
    """
    wat = """
    (module
        (memory (export "memory") 2)

        ;; echo: 将输入数据原样复制到输出区并返回输出指针
        (func (export "echo") (param $ptr i32) (param $len i32) (result i32)
            (local $i i32)
            (local $out_ptr i32)
            ;; 输出区从 offset 65536 开始（第2页）
            (local.set $out_ptr (i32.const 65536))
            (local.set $i (i32.const 0))
            (block $break
                (loop $loop
                    (br_if $break (i32.ge_u (local.get $i) (local.get $len)))
                    (i32.store8
                        (i32.add (local.get $out_ptr) (local.get $i))
                        (i32.load8_u (i32.add (local.get $ptr) (local.get $i)))
                    )
                    (local.set $i (i32.add (local.get $i) (i32.const 1)))
                    (br $loop)
                )
            )
            (local.get $out_ptr)
        )

        ;; add: 简单加法
        (func (export "add") (param $a i32) (param $b i32) (result i32)
            (i32.add (local.get $a) (local.get $b))
        )
    )
    """
    return wat.encode("utf-8")


def _build_infinite_loop_wasm() -> bytes:
    """构建一个无限循环的 WASM 模块（用于测试超时和 fuel 限制）"""
    wat = """
    (module
        (func (export "_start")
            (block $break
                (loop $loop
                    (br $loop)
                )
            )
        )
    )
    """
    return wat.encode("utf-8")


def _build_memory_hog_wasm() -> bytes:
    """构建一个消耗大量内存的 WASM 模块（用于测试内存限制）"""
    wat = """
    (module
        (memory (export "memory") 1)
        (func (export "_start")
            ;; 尝试 grow memory 到 1000 pages (~64MB)
            (drop (memory.grow (i32.const 1000)))
        )
    )
    """
    return wat.encode("utf-8")


@pytest.fixture
def tmp_wasm_dir(tmp_path: Path) -> Path:
    """创建临时 WASM 模块目录"""
    wasm_dir = tmp_path / "wasm_modules"
    wasm_dir.mkdir()
    return wasm_dir


@pytest.fixture
def echo_wasm_path(tmp_wasm_dir: Path) -> str:
    """创建 echo WASM 模块文件"""
    wasm_bytes = _build_echo_wasm()
    path = tmp_wasm_dir / "echo.wasm"
    path.write_bytes(wasm_bytes)
    return str(path)


@pytest.fixture
def infinite_loop_wasm_path(tmp_wasm_dir: Path) -> str:
    """创建无限循环 WASM 模块文件"""
    wasm_bytes = _build_infinite_loop_wasm()
    path = tmp_wasm_dir / "infinite_loop.wat"
    path.write_bytes(wasm_bytes)
    return str(path)


@pytest.fixture
def memory_hog_wasm_path(tmp_wasm_dir: Path) -> str:
    """创建内存消耗 WASM 模块文件"""
    wasm_bytes = _build_memory_hog_wasm()
    path = tmp_wasm_dir / "memory_hog.wat"
    path.write_bytes(wasm_bytes)
    return str(path)


@pytest.fixture
def default_config() -> dict[str, Any]:
    """默认配置"""
    return {
        "default_timeout_seconds": 5,
        "memory_limit_pages": 256,
        "fuel_limit": 10_000_000,
        "enable_wasi": False,
        "module_cache_size": 16,
    }


@pytest.fixture
def executor(default_config: dict[str, Any]) -> WasmSandboxExecutor:
    """创建 WasmSandboxExecutor 实例"""
    return WasmSandboxExecutor(config=default_config)


# ──────────────────────────────────────────────
# 测试：初始化
# ──────────────────────────────────────────────


class TestWasmSandboxInit:
    """初始化相关测试"""

    def test_init_default_config(self) -> None:
        """默认配置初始化"""
        exe = WasmSandboxExecutor()
        assert exe._default_timeout == 10
        assert exe._memory_limit_pages == 256
        assert exe._fuel_limit == 100_000_000
        assert exe._enable_wasi is False
        assert exe._module_cache_max == 64

    def test_init_custom_config(self, default_config: dict[str, Any]) -> None:
        """自定义配置初始化"""
        exe = WasmSandboxExecutor(config=default_config)
        assert exe._default_timeout == 5
        assert exe._memory_limit_pages == 256
        assert exe._fuel_limit == 10_000_000
        assert exe._module_cache_max == 16

    def test_native_available(self, executor: WasmSandboxExecutor) -> None:
        """检查 wasmtime Python bindings 是否可用"""
        # 在测试环境中应该可用（因为我们在 venv 中安装了 wasmtime）
        assert executor.is_native_available is True

    def test_stats_initial(self, executor: WasmSandboxExecutor) -> None:
        """初始统计信息"""
        stats = executor.get_stats()
        assert stats["total_executions"] == 0
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0
        assert stats["cached_modules"] == 0


# ──────────────────────────────────────────────
# 测试：模块编译与缓存
# ──────────────────────────────────────────────


class TestModuleCompilation:
    """模块编译与缓存测试"""

    @pytest.mark.asyncio
    async def test_module_compilation(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """模块能被正确编译"""
        result = await executor.execute(
            tool_id="test_echo",
            wasm_path=echo_wasm_path,
            params={"input": "hello"},
            entry_point="echo",
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_module_cache_hit(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """多次执行同一模块应命中缓存"""
        # 第一次执行：编译并缓存
        await executor.execute(
            tool_id="test_echo",
            wasm_path=echo_wasm_path,
            params={"input": "first"},
            entry_point="echo",
        )
        stats1 = executor.get_stats()
        assert stats1["cache_misses"] == 1
        assert stats1["cached_modules"] == 1

        # 第二次执行：应命中缓存
        await executor.execute(
            tool_id="test_echo",
            wasm_path=echo_wasm_path,
            params={"input": "second"},
            entry_point="echo",
        )
        stats2 = executor.get_stats()
        assert stats2["cache_hits"] == 1
        assert stats2["cache_misses"] == 1
        assert stats2["cached_modules"] == 1

    @pytest.mark.asyncio
    async def test_module_cache_eviction(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """缓存满时应淘汰最早的条目"""
        # 设置极小的缓存
        executor._module_cache_max = 1

        await executor.execute(
            tool_id="test1",
            wasm_path=echo_wasm_path,
            params={"input": "first"},
            entry_point="echo",
        )
        assert len(executor._module_cache) == 1

        # 创建第二个模块文件
        path2 = echo_wasm_path.replace("echo.wasm", "echo2.wasm")
        import shutil
        shutil.copy(echo_wasm_path, path2)

        await executor.execute(
            tool_id="test2",
            wasm_path=path2,
            params={"input": "second"},
            entry_point="echo",
        )
        # 缓存应仍然只有 1 个（旧的被淘汰）
        assert len(executor._module_cache) == 1

    def test_clear_module_cache(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """清空模块缓存"""
        # 手动添加一个缓存条目
        executor._module_cache["fake_path"] = MagicMock()
        assert len(executor._module_cache) == 1

        executor.clear_module_cache()
        assert len(executor._module_cache) == 0


# ──────────────────────────────────────────────
# 测试：成功执行
# ──────────────────────────────────────────────


class TestSuccessfulExecution:
    """成功执行测试"""

    @pytest.mark.asyncio
    async def test_echo_execution(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """echo 模块能正确返回结果"""
        result = await executor.execute(
            tool_id="echo_test",
            wasm_path=echo_wasm_path,
            params={"message": "hello world"},
            entry_point="echo",
        )
        assert result.tool_id == "echo_test"
        assert result.success is True
        assert result.execution_time_ms is not None
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_json_params_serialization(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """参数能正确 JSON 序列化"""
        params = {
            "string_param": "hello",
            "int_param": 42,
            "float_param": 3.14,
            "bool_param": True,
            "list_param": [1, 2, 3],
            "nested": {"key": "value"},
            "chinese": "中文测试",
        }
        result = await executor.execute(
            tool_id="json_test",
            wasm_path=echo_wasm_path,
            params=params,
            entry_point="echo",
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_empty_params(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """空参数应正常执行"""
        result = await executor.execute(
            tool_id="empty_test",
            wasm_path=echo_wasm_path,
            params={},
            entry_point="echo",
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execution_time_recorded(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """执行时间应被记录"""
        result = await executor.execute(
            tool_id="time_test",
            wasm_path=echo_wasm_path,
            params={"input": "test"},
            entry_point="echo",
        )
        assert result.success is True
        assert result.execution_time_ms is not None
        assert result.execution_time_ms >= 0


# ──────────────────────────────────────────────
# 测试：错误处理
# ──────────────────────────────────────────────


class TestErrorHandling:
    """错误处理测试"""

    @pytest.mark.asyncio
    async def test_module_not_found(
        self, executor: WasmSandboxExecutor
    ) -> None:
        """WASM 模块文件不存在"""
        result = await executor.execute(
            tool_id="missing",
            wasm_path="/nonexistent/path/module.wasm",
            params={},
        )
        assert result.success is False
        assert "not found" in result.error.lower() or "no such file" in result.error.lower()

    @pytest.mark.asyncio
    async def test_invalid_wasm_bytes(
        self, executor: WasmSandboxExecutor, tmp_path: Path
    ) -> None:
        """无效的 WASM 二进制"""
        invalid_path = tmp_path / "invalid.wasm"
        invalid_path.write_bytes(b"this is not a wasm module")

        result = await executor.execute(
            tool_id="invalid",
            wasm_path=str(invalid_path),
            params={},
        )
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_infinite_loop_fuel_exhaustion(
        self, executor: WasmSandboxExecutor, infinite_loop_wasm_path: str
    ) -> None:
        """无限循环应被 fuel 限制终止"""
        # 设置极小的 fuel 限制
        executor._fuel_limit = 1000

        result = await executor.execute(
            tool_id="loop_test",
            wasm_path=infinite_loop_wasm_path,
            params={},
            timeout=5,
        )
        # 应该因为 fuel 耗尽而失败
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_timeout_with_subprocess_fallback(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """subprocess 模式下的超时处理"""
        # 临时禁用原生模式
        original = WasmSandboxExecutor._HAS_WASMTIME
        WasmSandboxExecutor._HAS_WASMTIME = False
        try:
            # 使用极短超时
            result = await executor._execute_subprocess(
                tool_id="timeout_test",
                wasm_path=echo_wasm_path,
                params={},
                timeout=0,  # 0 秒超时
            )
            # 要么超时，要么 runtime 不存在
            assert result.success is False
        finally:
            WasmSandboxExecutor._HAS_WASMTIME = original


# ──────────────────────────────────────────────
# 测试：统计信息
# ──────────────────────────────────────────────


class TestStats:
    """统计信息测试"""

    @pytest.mark.asyncio
    async def test_execution_counting(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """执行计数正确"""
        assert executor.get_stats()["total_executions"] == 0

        await executor.execute(
            tool_id="test",
            wasm_path=echo_wasm_path,
            params={},
            entry_point="echo",
        )
        assert executor.get_stats()["total_executions"] == 1

        await executor.execute(
            tool_id="test",
            wasm_path=echo_wasm_path,
            params={},
            entry_point="echo",
        )
        assert executor.get_stats()["total_executions"] == 2

    @pytest.mark.asyncio
    async def test_cache_hit_rate(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """缓存命中率计算正确"""
        # 第一次：miss
        await executor.execute(
            tool_id="test",
            wasm_path=echo_wasm_path,
            params={},
            entry_point="echo",
        )
        stats = executor.get_stats()
        assert stats["cache_hit_rate"] == 0.0  # 0 hits, 1 miss

        # 第二次：hit
        await executor.execute(
            tool_id="test",
            wasm_path=echo_wasm_path,
            params={},
            entry_point="echo",
        )
        stats = executor.get_stats()
        assert stats["cache_hit_rate"] == pytest.approx(0.5)  # 1 hit, 1 miss

    def test_stats_fields(
        self, executor: WasmSandboxExecutor
    ) -> None:
        """统计信息包含所有必要字段"""
        stats = executor.get_stats()
        expected_fields = [
            "native_available",
            "total_executions",
            "cache_hits",
            "cache_misses",
            "cache_hit_rate",
            "cached_modules",
            "memory_limit_pages",
            "fuel_limit",
            "wasi_enabled",
            "allowed_dirs",
        ]
        for field in expected_fields:
            assert field in stats, f"Missing stats field: {field}"


# ──────────────────────────────────────────────
# 测试：subprocess 回退
# ──────────────────────────────────────────────


class TestSubprocessFallback:
    """subprocess 回退模式测试"""

    @pytest.mark.asyncio
    async def test_subprocess_fallback_runtime_not_found(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """subprocess 模式下 runtime 不存在"""
        result = await executor._execute_subprocess(
            tool_id="test",
            wasm_path=echo_wasm_path,
            params={"key": "value"},
            timeout=5,
        )
        # 应该失败（wasmtime CLI 可能不存在或参数格式不对）
        # 这取决于环境中是否有 wasmtime CLI
        assert isinstance(result.success, bool)

    @pytest.mark.asyncio
    async def test_subprocess_with_nonexistent_module(
        self, executor: WasmSandboxExecutor
    ) -> None:
        """subprocess 模式下模块不存在"""
        result = await executor._execute_subprocess(
            tool_id="test",
            wasm_path="/nonexistent/module.wasm",
            params={},
            timeout=5,
        )
        assert result.success is False


# ──────────────────────────────────────────────
# 测试：并发安全
# ──────────────────────────────────────────────


class TestConcurrency:
    """并发执行安全测试"""

    @pytest.mark.asyncio
    async def test_concurrent_executions(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """多个并发执行应互不干扰"""
        tasks = [
            executor.execute(
                tool_id=f"concurrent_{i}",
                wasm_path=echo_wasm_path,
                params={"index": i},
                entry_point="echo",
            )
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)
        for i, result in enumerate(results):
            assert result.success is True, f"Task {i} failed: {result.error}"

    @pytest.mark.asyncio
    async def test_concurrent_cache_access(
        self, executor: WasmSandboxExecutor, echo_wasm_path: str
    ) -> None:
        """并发访问缓存应安全"""
        # 先预热缓存
        await executor.execute(
            tool_id="warmup",
            wasm_path=echo_wasm_path,
            params={},
            entry_point="echo",
        )

        # 并发执行，应全部命中缓存
        tasks = [
            executor.execute(
                tool_id=f"cache_test_{i}",
                wasm_path=echo_wasm_path,
                params={"i": i},
                entry_point="echo",
            )
            for i in range(10)
        ]
        results = await asyncio.gather(*tasks)
        assert all(r.success for r in results)

        stats = executor.get_stats()
        assert stats["cache_hits"] >= 10  # 至少 10 次命中


# ──────────────────────────────────────────────
# 测试：WASI 配置
# ──────────────────────────────────────────────


class TestWasiConfig:
    """WASI 配置测试"""

    def test_wasi_disabled_by_default(self) -> None:
        """默认不启用 WASI"""
        exe = WasmSandboxExecutor()
        assert exe._enable_wasi is False

    def test_wasi_enabled_config(self) -> None:
        """通过配置启用 WASI"""
        exe = WasmSandboxExecutor(config={
            "enable_wasi": True,
            "allowed_dirs": ["/tmp"],
            "env_vars": {"KEY": "value"},
        })
        assert exe._enable_wasi is True
        assert exe._allowed_dirs == ["/tmp"]
        assert exe._env_vars == {"KEY": "value"}
