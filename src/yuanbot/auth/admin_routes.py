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

import shutil
import sys
from datetime import datetime
from pathlib import Path

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

    备份 data/ 目录和 configs/ 目录。
    """
    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"
    backup_path = backup_dir / backup_name
    backup_path.mkdir()

    # 备份 data 目录（排除 backups 自身）
    data_dir = Path("data")
    if data_dir.exists():
        for item in data_dir.iterdir():
            if item.name == "backups":
                continue
            dest = backup_path / "data" / item.name
            if item.is_dir():
                shutil.copytree(str(item), str(dest))
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(item), str(dest))

    # 备份 configs 目录
    configs_dir = Path("configs")
    if configs_dir.exists():
        shutil.copytree(str(configs_dir), str(backup_path / "configs"))

    # 创建备份元数据
    meta = {
        "timestamp": timestamp,
        "created_by": admin.username,
        "includes": ["data", "configs"],
    }
    import json

    with open(backup_path / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("backup_created", path=str(backup_path), by=admin.username)
    return {"status": "ok", "backup": backup_name, "path": str(backup_path)}


@router.get("/backups")
async def list_backups(admin: User = Depends(require_admin)) -> dict:
    """列出所有备份"""
    import json

    backup_dir = Path("data/backups")
    if not backup_dir.exists():
        return {"backups": []}

    backups = []
    for d in sorted(backup_dir.iterdir(), reverse=True):
        if d.is_dir():
            meta_path = d / "meta.json"
            meta = {}
            if meta_path.exists():
                with open(meta_path) as f:
                    meta = json.load(f)
            backups.append({
                "name": d.name,
                "path": str(d),
                **meta,
            })

    return {"backups": backups}


@router.post("/restore")
async def restore_backup(request: dict, admin: User = Depends(require_admin)) -> dict:
    """从备份恢复"""
    backup_name = request.get("backup_name")
    if not backup_name:
        raise HTTPException(status_code=400, detail="backup_name is required")

    backup_path = Path("data/backups") / backup_name
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail=f"Backup '{backup_name}' not found")

    # 恢复 data
    backup_data = backup_path / "data"
    if backup_data.exists():
        data_dir = Path("data")
        for item in backup_data.iterdir():
            dest = data_dir / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(str(dest))
                else:
                    dest.unlink()
            if item.is_dir():
                shutil.copytree(str(item), str(dest))
            else:
                shutil.copy2(str(item), str(dest))

    # 恢复 configs
    backup_configs = backup_path / "configs"
    if backup_configs.exists():
        configs_dir = Path("configs")
        if configs_dir.exists():
            shutil.rmtree(str(configs_dir))
        shutil.copytree(str(backup_configs), str(configs_dir))

    logger.info("backup_restored", backup=backup_name, by=admin.username)
    return {"status": "ok", "message": f"已从备份 '{backup_name}' 恢复"}
