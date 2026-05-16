"""YuanBot 使用示例

演示如何使用 YuanBot 的核心功能。
"""

import asyncio
from yuanbot.core.types import (
    ContentType,
    UserMessage,
    MemoryNode,
    MemoryType,
)
from yuanbot.memory.manager import MemoryManager


async def memory_demo():
    """记忆系统演示"""
    print("🌸 YuanBot 记忆系统演示\n")

    memory = MemoryManager()

    # 1. 添加事实记忆
    print("1. 添加事实记忆...")
    await memory.add_fact_memory(
        user_id="demo_user",
        content="用户喜欢喝拿铁咖啡，不喜欢美式",
        key_entities=["拿铁", "咖啡"],
        importance=0.8,
    )
    await memory.add_fact_memory(
        user_id="demo_user",
        content="用户生日是6月15日",
        key_entities=["生日"],
        importance=0.9,
    )

    # 2. 添加情景记忆
    print("2. 添加情景记忆...")
    await memory.add_episodic_memory(
        user_id="demo_user",
        content="用户聊到最近工作压力大，项目快到截止日了",
        summary="工作压力对话 - 项目截止日临近",
        topic_tags=["工作", "压力"],
        emotional_tone="negative",
        key_entities=["项目截止日"],
    )
    await memory.add_episodic_memory(
        user_id="demo_user",
        content="用户说周末想去爬山放松",
        summary="周末计划 - 爬山放松",
        topic_tags=["周末", "运动", "放松"],
        emotional_tone="positive",
    )

    # 3. 情景触发式检索
    print("\n3. 情景触发式检索...")
    test_queries = [
        "今天想喝咖啡",
        "工作好累啊",
        "周末有什么安排",
    ]
    for query in test_queries:
        results = await memory.retrieve_relevant_memories(
            user_id="demo_user",
            current_input=query,
        )
        print(f"\n  查询: '{query}'")
        if results:
            for r in results[:2]:
                print(f"    → [{r.match_type}] {r.node.summary or r.node.content[:50]} "
                      f"(评分: {r.score:.2f})")
        else:
            print("    → 无匹配记忆")

    # 4. 用户画像
    print("\n4. 用户画像...")
    profile = await memory.get_or_create_user_profile("demo_user")
    print(f"  用户 ID: {profile.user_id}")
    print(f"  关系阶段: {profile.relationship_stage}")
    print(f"  交互次数: {profile.total_interactions}")
    print(f"  偏好: {profile.preferences}")

    # 5. 记忆固化
    print("\n5. 记忆固化...")
    # 先添加更多重复话题
    for i in range(3):
        await memory.add_episodic_memory(
            user_id="demo_user",
            content=f"用户第{i+1}次提到想学吉他",
            summary=f"学吉他讨论 {i+1}",
            topic_tags=["吉他"],
        )
    stats = await memory.consolidate_memories("demo_user")
    print(f"  升级为事实记忆: {stats['upgraded']} 条")

    print("\n✅ 演示完成！")


if __name__ == "__main__":
    asyncio.run(memory_demo())
