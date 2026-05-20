"""YuanBot 服务层

提供统一的业务服务接口，屏蔽底层实现细节。
"""

from yuanbot.services.ai_service import AIService

__all__ = ["AIService"]
