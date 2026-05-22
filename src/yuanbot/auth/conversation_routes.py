"""会话管理 API 路由

设计参考: user-interface-system.md 第7.2节

端点:
- GET    /api/conversations              获取当前用户的会话列表
- POST   /api/conversations              新建会话
- GET    /api/conversations/{id}         获取会话详情
- DELETE /api/conversations/{id}         删除会话
- GET    /api/conversations/{id}/messages 获取历史消息
- POST   /api/chat                       发送消息（与 AI 对话）
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from yuanbot.auth.middleware import get_current_user
from yuanbot.auth.models import User
from yuanbot.auth.store import ConversationStore

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["conversations"])


def _get_conv_store() -> ConversationStore:
    """获取会话存储（延迟导入避免循环）"""
    from yuanbot.auth.middleware import get_auth_manager

    return get_auth_manager()._user_store  # 实际用独立的 conv_store


# 全局 conversation store 实例（在 app.py 中初始化）
_conv_store: ConversationStore | None = None


def init_conversation_store(store: ConversationStore) -> None:
    """初始化会话存储"""
    global _conv_store
    _conv_store = store


def get_conv_store() -> ConversationStore:
    if _conv_store is None:
        raise RuntimeError("ConversationStore not initialized")
    return _conv_store


class CreateConversationRequest(BaseModel):
    title: str = "新会话"


class SendMessageRequest(BaseModel):
    content: str
    conversation_id: str | None = None  # 不指定则使用最近会话或新建


@router.get("/api/conversations")
async def list_conversations(user: User = Depends(get_current_user)) -> dict:
    """获取当前用户的会话列表"""
    store = get_conv_store()
    convs = store.list_conversations(user.user_id)
    return {
        "conversations": [
            {
                "conversation_id": c.conversation_id,
                "title": c.title,
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat(),
                "message_count": c.message_count,
            }
            for c in convs
        ]
    }


@router.post("/api/conversations")
async def create_conversation(
    body: CreateConversationRequest,
    user: User = Depends(get_current_user),
) -> dict:
    """新建会话"""
    store = get_conv_store()
    conv = store.create_conversation(user.user_id, title=body.title)
    return {
        "conversation_id": conv.conversation_id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat(),
    }


@router.get("/api/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """获取会话详情（校验归属）"""
    store = get_conv_store()
    conv = store.get_conversation(conversation_id, user.user_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "conversation_id": conv.conversation_id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
        "message_count": conv.message_count,
    }


@router.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """删除会话（校验归属）"""
    store = get_conv_store()
    if not store.delete_conversation(conversation_id, user.user_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok"}


@router.get("/api/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
) -> dict:
    """获取会话历史消息（校验归属）"""
    store = get_conv_store()
    conv = store.get_conversation(conversation_id, user.user_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = store.get_messages(conversation_id, user.user_id, limit=limit, offset=offset)
    return {
        "messages": [
            {
                "message_id": m.message_id,
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in messages
        ],
        "total": conv.message_count,
    }


@router.post("/api/chat")
async def send_message(
    body: SendMessageRequest,
    user: User = Depends(get_current_user),
) -> dict:
    """发送消息并获取 AI 回复

    流程：
    1. 确定会话（使用指定的或新建）
    2. 保存用户消息
    3. 调用编排引擎生成回复
    4. 保存 AI 回复
    5. 返回响应
    """
    store = get_conv_store()

    # 确定会话
    conversation_id = body.conversation_id
    if not conversation_id:
        # 创建新会话
        conv = store.create_conversation(user.user_id)
        conversation_id = conv.conversation_id
    else:
        conv = store.get_conversation(conversation_id, user.user_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

    # 保存用户消息
    user_msg = store.add_message(
        conversation_id=conversation_id,
        user_id=user.user_id,
        role="user",
        content=body.content,
    )

    # 调用编排引擎（如果可用）
    ai_reply = await _generate_ai_reply(user, body.content, conversation_id)

    # 保存 AI 回复
    ai_msg = store.add_message(
        conversation_id=conversation_id,
        user_id=user.user_id,
        role="assistant",
        content=ai_reply,
    )

    return {
        "conversation_id": conversation_id,
        "user_message": {
            "message_id": user_msg.message_id if user_msg else None,
            "content": body.content,
        },
        "ai_message": {
            "message_id": ai_msg.message_id if ai_msg else None,
            "content": ai_reply,
        },
    }


async def _generate_ai_reply(user: User, message: str, conversation_id: str) -> str:
    """调用编排引擎生成 AI 回复

    如果编排引擎不可用，返回兜底回复。
    """
    try:
        # 尝试获取编排引擎（从 app.state）
        from fastapi import Request

        # 通过全局引用获取
        from yuanbot.auth.middleware import get_auth_manager

        # 这里需要一个方式访问 app.state，暂时用兜底
        # 实际集成时通过依赖注入
        return f"收到你的消息了：「{message}」。AI 编排引擎集成后将提供完整回复。"
    except Exception as e:
        logger.error("ai_reply_error", error=str(e))
        return "抱歉，AI 服务暂时不可用，请稍后再试。"
