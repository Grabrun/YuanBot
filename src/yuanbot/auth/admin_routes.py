"""管理 API 路由

设计参考: user-interface-system.md 第7.3节

端点:
- GET    /api/admin/users                用户列表
- POST   /api/admin/users                创建用户
- DELETE /api/admin/users/{id}           删除用户
- POST   /api/admin/users/{id}/api-key   生成 API Key
- DELETE /api/admin/users/{id}/api-key   吊销 API Key
- GET    /api/admin/metrics              系统指标
"""

from __future__ import annotations

import sys

import structlog
from fastapi import APIRouter, Depends, HTTPException

from yuanbot.auth.middleware import require_admin
from yuanbot.auth.models import CreateUserRequest, User
from yuanbot.auth.store import ConversationStore, UserStore

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# 全局引用（在 app.py 中设置）
_user_store: UserStore | None = None
_conv_store: ConversationStore | None = None


def init_admin_stores(user_store: UserStore, conv_store: ConversationStore) -> None:
    """初始化管理路由的存储引用"""
    global _user_store, _conv_store
    _user_store = user_store
    _conv_store = conv_store


def _get_user_store() -> UserStore:
    if _user_store is None:
        raise RuntimeError("UserStore not initialized")
    return _user_store


def _get_conv_store() -> ConversationStore:
    if _conv_store is None:
        raise RuntimeError("ConversationStore not initialized")
    return _conv_store


# ── 用户管理 ──────────────────────────────────


@router.get("/users")
async def list_users(admin: User = Depends(require_admin)) -> dict:
    """列出所有用户"""
    store = _get_user_store()
    users = store.list_users()
    return {
        "users": [u.to_safe_dict() for u in users],
        "total": len(users),
    }


@router.post("/users")
async def create_user(
    body: CreateUserRequest,
    admin: User = Depends(require_admin),
) -> dict:
    """创建新用户"""
    store = _get_user_store()
    try:
        user = store.create_user(
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            role=body.role,
        )
        return {"user": user.to_safe_dict()}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
) -> dict:
    """删除用户"""
    store = _get_user_store()

    # 不允许删除自己
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    if not store.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "ok"}


# ── API Key 管理 ──────────────────────────────


@router.post("/users/{user_id}/api-key")
async def generate_api_key(
    user_id: str,
    admin: User = Depends(require_admin),
) -> dict:
    """为用户生成 API Key"""
    store = _get_user_store()
    user = store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    api_key = store.set_api_key(user_id)
    return {"api_key": api_key, "user_id": user_id}


@router.delete("/users/{user_id}/api-key")
async def revoke_api_key(
    user_id: str,
    admin: User = Depends(require_admin),
) -> dict:
    """吊销用户的 API Key"""
    store = _get_user_store()
    if not store.revoke_api_key(user_id):
        raise HTTPException(status_code=404, detail="User not found or no API key")
    return {"status": "ok"}


# ── 系统指标 ──────────────────────────────────


@router.get("/metrics")
async def get_system_metrics(admin: User = Depends(require_admin)) -> dict:
    """获取系统指标"""
    user_store = _get_user_store()
    conv_store = _get_conv_store()

    # 基础指标
    cpu_percent = 0
    memory = None
    disk = None

    try:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
    except ImportError:
        pass

    return {
        "system": {
            "python_version": sys.version,
            "platform": sys.platform,
            "cpu_percent": cpu_percent,
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2) if memory else None,
                "used_percent": memory.percent if memory else None,
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2) if disk else None,
                "used_percent": round(disk.percent, 1) if disk else None,
            },
        },
        "yuanbot": {
            "users": {
                "total": user_store.user_count,
                "admin": user_store.admin_count,
            },
            "conversations": {
                "total": conv_store.conversation_count,
                "messages": conv_store.total_message_count,
            },
        },
    }


# ── 备份与恢复 ──────────────────────────────


@router.post("/backup")
async def trigger_backup(admin: User = Depends(require_admin)) -> dict:
    """触发系统备份

    使用 BackupManager 创建 tar.gz 归档备份。
    """
    from yuanbot.infrastructure.backup import BackupManager

    manager = BackupManager()
    result = manager.create_backup(
        include_logs=False,
        description="API 触发备份",
        created_by=admin.username,
    )

    logger.info("backup_created", name=result["name"], by=admin.username)
    return {"status": "ok", **result}


@router.get("/backups")
async def list_backups(admin: User = Depends(require_admin)) -> dict:
    """列出所有备份"""
    from yuanbot.infrastructure.backup import BackupManager

    manager = BackupManager()
    backups = manager.list_backups()
    return {"backups": backups, "total": len(backups)}


@router.post("/restore")
async def restore_backup(request: dict, admin: User = Depends(require_admin)) -> dict:
    """从备份恢复"""
    from yuanbot.infrastructure.backup import BackupManager

    backup_name = request.get("backup_name")
    if not backup_name:
        raise HTTPException(status_code=400, detail="backup_name is required")

    manager = BackupManager()
    result = manager.restore_backup(
        backup_name=backup_name,
        restore_data=True,
        restore_configs=True,
        dry_run=request.get("dry_run", False),
    )

    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])

    logger.info("backup_restored", name=backup_name, by=admin.username)
    return {"status": "ok", **result}


# ── 日志管理 ──────────────────────────────────


@router.get("/logging/status")
async def get_logging_status(admin: User = Depends(require_admin)) -> dict:
    """获取当前日志配置状态"""
    from yuanbot.infrastructure.logging_config import get_log_status

    return get_log_status()


@router.put("/logging/level")
async def set_logging_level(
    body: dict,
    admin: User = Depends(require_admin),
) -> dict:
    """动态调整日志级别

    请求体:
        {"level": "DEBUG"}
    """
    level = body.get("level")
    if not level:
        raise HTTPException(status_code=400, detail="level is required")

    from yuanbot.infrastructure.logging_config import set_log_level

    result = set_log_level(level)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))

    logger.info("log_level_changed", by=admin.username, level=level)
    return result
