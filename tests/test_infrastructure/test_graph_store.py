"""知识图谱存储测试"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from yuanbot.infrastructure.graph_store import GraphStore, InMemoryGraph


class TestInMemoryGraph:
    """内存图数据结构测试"""

    def test_empty_graph(self):
        graph = InMemoryGraph()
        assert graph.nodes == {}
        assert graph.edges == {}


class TestGraphStoreMemoryMode:
    """内存模式下的 GraphStore 测试"""

    @pytest.fixture
    def store(self):
        """创建内存模式的 GraphStore"""
        return GraphStore(db_path=None)

    @pytest.mark.asyncio
    async def test_init_memory_mode(self, store):
        assert store.is_kuzu is False

    @pytest.mark.asyncio
    async def test_add_node(self, store):
        node_id = await store.add_node(
            node_id="user1",
            node_type="User",
            properties={"name": "小明"},
        )
        assert node_id == "user1"
        assert "user1" in store._memory_graph.nodes

    @pytest.mark.asyncio
    async def test_add_node_auto_id(self, store):
        node_id = await store.add_node(
            node_id="",
            node_type="Entity",
            properties={"name": "咖啡", "type": "food"},
        )
        assert node_id != ""
        assert len(node_id) > 0

    @pytest.mark.asyncio
    async def test_add_edge(self, store):
        await store.add_node("user1", "User", {"name": "小明"})
        await store.add_node("entity1", "Entity", {"name": "咖啡", "type": "food"})

        edge_id = await store.add_edge(
            source_id="user1",
            target_id="entity1",
            edge_type="LIKES",
            properties={"weight": 0.9},
        )
        assert edge_id != ""
        assert edge_id in store._memory_graph.edges

    @pytest.mark.asyncio
    async def test_get_neighbors_outgoing(self, store):
        await store.add_node("user1", "User", {"name": "小明"})
        await store.add_node("coffee", "Entity", {"name": "咖啡", "type": "food"})
        await store.add_node("tea", "Entity", {"name": "茶", "type": "food"})

        await store.add_edge("user1", "coffee", "LIKES", {"weight": 0.9})
        await store.add_edge("user1", "tea", "LIKES", {"weight": 0.7})

        neighbors = await store.get_neighbors("user1", direction="outgoing")
        assert len(neighbors) == 2
        neighbor_ids = {n["node_id"] for n in neighbors}
        assert "coffee" in neighbor_ids
        assert "tea" in neighbor_ids

    @pytest.mark.asyncio
    async def test_get_neighbors_incoming(self, store):
        await store.add_node("user1", "User", {"name": "小明"})
        await store.add_node("trait1", "Trait", {"name": "善良", "value": "high"})

        await store.add_edge("user1", "trait1", "HAS_TRAIT")

        # 从 trait1 看 incoming
        neighbors = await store.get_neighbors("trait1", direction="incoming")
        assert len(neighbors) == 1
        assert neighbors[0]["node_id"] == "user1"

    @pytest.mark.asyncio
    async def test_get_neighbors_both(self, store):
        await store.add_node("e1", "Entity", {"name": "A"})
        await store.add_node("e2", "Entity", {"name": "B"})
        await store.add_node("e3", "Entity", {"name": "C"})

        await store.add_edge("e1", "e2", "ASSOCIATED_WITH")
        await store.add_edge("e3", "e1", "ASSOCIATED_WITH")

        neighbors = await store.get_neighbors("e1", direction="both")
        assert len(neighbors) == 2

    @pytest.mark.asyncio
    async def test_get_neighbors_filter_edge_type(self, store):
        await store.add_node("user1", "User", {"name": "小明"})
        await store.add_node("coffee", "Entity", {"name": "咖啡"})
        await store.add_node("trait1", "Trait", {"name": "外向", "value": "high"})

        await store.add_edge("user1", "coffee", "LIKES", {"weight": 0.9})
        await store.add_edge("user1", "trait1", "HAS_TRAIT")

        # 只查 LIKES 关系
        neighbors = await store.get_neighbors("user1", edge_type="LIKES", direction="outgoing")
        assert len(neighbors) == 1
        assert neighbors[0]["node_id"] == "coffee"

        # 只查 HAS_TRAIT 关系
        neighbors = await store.get_neighbors("user1", edge_type="HAS_TRAIT", direction="outgoing")
        assert len(neighbors) == 1
        assert neighbors[0]["node_id"] == "trait1"

    @pytest.mark.asyncio
    async def test_get_neighbors_nonexistent_node(self, store):
        neighbors = await store.get_neighbors("nonexistent", direction="outgoing")
        assert neighbors == []

    @pytest.mark.asyncio
    async def test_find_path_direct(self, store):
        await store.add_node("a", "Entity", {"name": "A"})
        await store.add_node("b", "Entity", {"name": "B"})
        await store.add_edge("a", "b", "ASSOCIATED_WITH")

        paths = await store.find_path("a", "b", max_depth=3)
        assert len(paths) >= 1
        assert paths[0] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_find_path_indirect(self, store):
        await store.add_node("a", "Entity", {"name": "A"})
        await store.add_node("b", "Entity", {"name": "B"})
        await store.add_node("c", "Entity", {"name": "C"})

        await store.add_edge("a", "b", "ASSOCIATED_WITH")
        await store.add_edge("b", "c", "ASSOCIATED_WITH")

        paths = await store.find_path("a", "c", max_depth=3)
        assert len(paths) >= 1
        assert paths[0] == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_find_path_same_node(self, store):
        await store.add_node("a", "Entity", {"name": "A"})
        paths = await store.find_path("a", "a", max_depth=3)
        assert paths == [["a"]]

    @pytest.mark.asyncio
    async def test_find_path_no_path(self, store):
        await store.add_node("a", "Entity", {"name": "A"})
        await store.add_node("b", "Entity", {"name": "B"})
        # 没有边连接
        paths = await store.find_path("a", "b", max_depth=3)
        assert paths == []

    @pytest.mark.asyncio
    async def test_find_path_max_depth(self, store):
        await store.add_node("a", "Entity", {"name": "A"})
        await store.add_node("b", "Entity", {"name": "B"})
        await store.add_node("c", "Entity", {"name": "C"})
        await store.add_node("d", "Entity", {"name": "D"})

        await store.add_edge("a", "b", "ASSOCIATED_WITH")
        await store.add_edge("b", "c", "ASSOCIATED_WITH")
        await store.add_edge("c", "d", "ASSOCIATED_WITH")

        # max_depth=2 应该找不到 a->d (需要 3 步)
        paths = await store.find_path("a", "d", max_depth=2)
        assert paths == []

        # max_depth=3 应该找到
        paths = await store.find_path("a", "d", max_depth=3)
        assert len(paths) >= 1

    @pytest.mark.asyncio
    async def test_get_user_relationships(self, store):
        await store.add_node("user1", "User", {"name": "小明"})
        await store.add_node("coffee", "Entity", {"name": "咖啡"})
        await store.add_node("trait1", "Trait", {"name": "善良"})

        await store.add_edge("user1", "coffee", "LIKES", {"weight": 0.9})
        await store.add_edge("user1", "trait1", "HAS_TRAIT")

        rels = await store.get_user_relationships("user1")
        assert "LIKES" in rels
        assert "HAS_TRAIT" in rels
        assert len(rels["LIKES"]) == 1
        assert len(rels["HAS_TRAIT"]) == 1

    @pytest.mark.asyncio
    async def test_get_user_relationships_empty(self, store):
        await store.add_node("user1", "User", {"name": "小明"})
        rels = await store.get_user_relationships("user1")
        assert rels == {}

    @pytest.mark.asyncio
    async def test_update_relationship(self, store):
        await store.add_node("user1", "User", {"name": "小明"})
        await store.add_node("coffee", "Entity", {"name": "咖啡"})

        edge_id = await store.add_edge("user1", "coffee", "LIKES", {"weight": 0.5})
        result = await store.update_relationship(edge_id, {"weight": 0.95})
        assert result is True
        assert store._memory_graph.edges[edge_id]["properties"]["weight"] == 0.95

    @pytest.mark.asyncio
    async def test_update_relationship_nonexistent(self, store):
        result = await store.update_relationship("nonexistent", {"weight": 0.9})
        assert result is False

    @pytest.mark.asyncio
    async def test_get_node(self, store):
        await store.add_node("user1", "User", {"name": "小明"})
        node = await store.get_node("user1")
        assert node is not None
        assert node["id"] == "user1"
        assert node["type"] == "User"

    @pytest.mark.asyncio
    async def test_get_node_nonexistent(self, store):
        node = await store.get_node("nonexistent")
        assert node is None

    @pytest.mark.asyncio
    async def test_remove_node(self, store):
        await store.add_node("user1", "User", {"name": "小明"})
        await store.add_node("coffee", "Entity", {"name": "咖啡"})
        await store.add_edge("user1", "coffee", "LIKES")

        result = await store.remove_node("user1")
        assert result is True
        assert await store.get_node("user1") is None
        # 关联边也应该被删除
        assert len(store._memory_graph.edges) == 0

    @pytest.mark.asyncio
    async def test_remove_node_nonexistent(self, store):
        result = await store.remove_node("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_edge(self, store):
        await store.add_node("a", "Entity", {"name": "A"})
        await store.add_node("b", "Entity", {"name": "B"})
        edge_id = await store.add_edge("a", "b", "ASSOCIATED_WITH")

        result = await store.remove_edge(edge_id)
        assert result is True
        assert edge_id not in store._memory_graph.edges

    @pytest.mark.asyncio
    async def test_remove_edge_nonexistent(self, store):
        result = await store.remove_edge("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_all_nodes(self, store):
        await store.add_node("u1", "User", {"name": "小明"})
        await store.add_node("e1", "Entity", {"name": "咖啡"})
        await store.add_node("t1", "Trait", {"name": "善良"})

        all_nodes = await store.get_all_nodes()
        assert len(all_nodes) == 3

    @pytest.mark.asyncio
    async def test_get_all_nodes_filtered(self, store):
        await store.add_node("u1", "User", {"name": "小明"})
        await store.add_node("e1", "Entity", {"name": "咖啡"})
        await store.add_node("t1", "Trait", {"name": "善良"})

        users = await store.get_all_nodes(node_type="User")
        assert len(users) == 1
        assert users[0]["type"] == "User"

    @pytest.mark.asyncio
    async def test_close_memory_mode(self, store):
        await store.add_node("u1", "User", {"name": "小明"})
        await store.close()
        assert store._memory_graph.nodes == {}

    @pytest.mark.asyncio
    async def test_escape(self, store):
        """测试单引号转义"""
        node_id = await store.add_node(
            node_id="test",
            node_type="User",
            properties={"name": "O'Brien"},
        )
        assert node_id == "test"

    @pytest.mark.asyncio
    async def test_multiple_edge_types(self, store):
        """测试多种关系类型"""
        await store.add_node("user1", "User", {"name": "小明"})
        await store.add_node("food", "Entity", {"name": "火锅"})
        await store.add_node("music", "Entity", {"name": "古典音乐"})
        await store.add_node("work", "Entity", {"name": "编程"})

        await store.add_edge("user1", "food", "LIKES", {"weight": 0.95})
        await store.add_edge("user1", "music", "DISLIKES", {"weight": 0.3})
        await store.add_edge("user1", "work", "EXPERIENCED")

        rels = await store.get_user_relationships("user1")
        assert len(rels) == 3
        assert "LIKES" in rels
        assert "DISLIKES" in rels
        assert "EXPERIENCED" in rels

    @pytest.mark.asyncio
    async def test_find_path_multiple_routes(self, store):
        """测试多条路径"""
        await store.add_node("a", "Entity", {"name": "A"})
        await store.add_node("b", "Entity", {"name": "B"})
        await store.add_node("c", "Entity", {"name": "C"})
        await store.add_node("d", "Entity", {"name": "D"})

        # a -> b -> d 和 a -> c -> d
        await store.add_edge("a", "b", "ASSOCIATED_WITH")
        await store.add_edge("b", "d", "ASSOCIATED_WITH")
        await store.add_edge("a", "c", "ASSOCIATED_WITH")
        await store.add_edge("c", "d", "ASSOCIATED_WITH")

        paths = await store.find_path("a", "d", max_depth=3)
        assert len(paths) >= 2
        path_strs = ["".join(p) for p in paths]
        assert "abd" in path_strs
        assert "acd" in path_strs

    @pytest.mark.asyncio
    async def test_in_relationship_with(self, store):
        """测试 IN_RELATIONSHIP_WITH 关系类型"""
        await store.add_node("user1", "User", {"name": "小明"})
        await store.add_node("persona1", "AIPersona", {"name": "小缘"})

        edge_id = await store.add_edge(
            "user1", "persona1", "IN_RELATIONSHIP_WITH",
            {"stage": "familiar", "since": "2026-01-01"},
        )
        assert edge_id != ""

        neighbors = await store.get_neighbors("user1", edge_type="IN_RELATIONSHIP_WITH")
        assert len(neighbors) == 1
        assert neighbors[0]["node_id"] == "persona1"
        assert neighbors[0]["edge_properties"]["stage"] == "familiar"

    @pytest.mark.asyncio
    async def test_knows_about(self, store):
        """测试 KNOWS_ABOUT 关系类型"""
        await store.add_node("persona1", "AIPersona", {"name": "小缘"})
        await store.add_node("entity1", "Entity", {"name": "咖啡", "type": "food"})

        edge_id = await store.add_edge("persona1", "entity1", "KNOWS_ABOUT")
        assert edge_id != ""

        neighbors = await store.get_neighbors("persona1", edge_type="KNOWS_ABOUT")
        assert len(neighbors) == 1
        assert neighbors[0]["node_id"] == "entity1"

    @pytest.mark.asyncio
    async def test_aipersona_node(self, store):
        """测试 AIPersona 节点类型"""
        node_id = await store.add_node(
            "persona1", "AIPersona", {"name": "小缘"},
        )
        assert node_id == "persona1"

        node = await store.get_node("persona1")
        assert node is not None
        assert node["type"] == "AIPersona"

        all_personas = await store.get_all_nodes(node_type="AIPersona")
        assert len(all_personas) == 1


class TestGraphStoreReasoning:
    """图推理方法测试"""

    @pytest.fixture
    def store(self):
        return GraphStore(db_path=None)

    async def _build_test_graph(self, store: GraphStore) -> None:
        """构建测试图谱"""
        # 用户
        await store.add_node("user1", "User", {"name": "小明"})
        await store.add_node("user2", "User", {"name": "小红"})

        # 实体
        await store.add_node("coffee", "Entity", {"name": "咖啡", "type": "food"})
        await store.add_node("tea", "Entity", {"name": "茶", "type": "food"})
        await store.add_node("coding", "Entity", {"name": "编程", "type": "activity"})
        await store.add_node("python", "Entity", {"name": "Python", "type": "technology"})
        await store.add_node("music", "Entity", {"name": "古典音乐", "type": "music"})

        # 人格
        await store.add_node("persona1", "AIPersona", {"name": "小缘"})

        # 关系
        await store.add_edge("user1", "coffee", "LIKES", {"weight": 0.9})
        await store.add_edge("user1", "coding", "LIKES", {"weight": 0.95})
        await store.add_edge("user1", "music", "DISLIKES", {"weight": 0.3})
        await store.add_edge("user2", "coffee", "LIKES", {"weight": 0.8})
        await store.add_edge("user2", "tea", "LIKES", {"weight": 0.7})
        await store.add_edge("coding", "python", "ASSOCIATED_WITH", {"strength": 0.9})
        await store.add_edge("user1", "persona1", "IN_RELATIONSHIP_WITH", {"stage": "familiar"})
        await store.add_edge("persona1", "coffee", "KNOWS_ABOUT")

    @pytest.mark.asyncio
    async def test_find_related_entities_basic(self, store):
        """测试基本的多跳实体查找"""
        await self._build_test_graph(store)

        results = await store.find_related_entities("user1", max_depth=1)
        entity_ids = {r["entity_id"] for r in results}
        # user1 -> coffee, coding (LIKES), music (DISLIKES)
        assert "coffee" in entity_ids
        assert "coding" in entity_ids
        assert "music" in entity_ids

    @pytest.mark.asyncio
    async def test_find_related_entities_two_hops(self, store):
        """测试两跳推理"""
        await self._build_test_graph(store)

        results = await store.find_related_entities("user1", max_depth=2)
        entity_ids = {r["entity_id"] for r in results}
        # user1 -> coding -> python (两跳)
        assert "python" in entity_ids

    @pytest.mark.asyncio
    async def test_find_related_entities_weight_filter(self, store):
        """测试权重过滤"""
        await self._build_test_graph(store)

        # 只取权重 >= 0.9 的
        results = await store.find_related_entities("user1", min_weight=0.9, max_depth=1)
        entity_ids = {r["entity_id"] for r in results}
        assert "coffee" in entity_ids  # weight=0.9
        assert "coding" in entity_ids  # weight=0.95
        # music 是 DISLIKES weight=0.3，但默认也查 DISLIKES，权重 < 0.9 被过滤
        assert "music" not in entity_ids

    @pytest.mark.asyncio
    async def test_find_related_entities_relation_filter(self, store):
        """测试关系类型过滤"""
        await self._build_test_graph(store)

        results = await store.find_related_entities(
            "user1", relation_types=["LIKES"], max_depth=1,
        )
        entity_ids = {r["entity_id"] for r in results}
        assert "coffee" in entity_ids
        assert "coding" in entity_ids
        assert "music" not in entity_ids  # DISLIKES 被排除

    @pytest.mark.asyncio
    async def test_find_related_entities_path_and_chain(self, store):
        """测试路径和关系链记录"""
        await self._build_test_graph(store)

        results = await store.find_related_entities("user1", max_depth=2)
        # 找 python 的结果应该有完整的路径和关系链
        python_results = [r for r in results if r["entity_id"] == "python"]
        assert len(python_results) >= 1
        r = python_results[0]
        assert r["path"] == ["user1", "coding", "python"]
        assert r["relation_chain"] == ["LIKES", "ASSOCIATED_WITH"]
        assert r["depth"] == 2

    @pytest.mark.asyncio
    async def test_get_entity_connections(self, store):
        """测试实体连接查询"""
        await self._build_test_graph(store)

        result = await store.get_entity_connections("coffee")
        assert result["node"] is not None
        assert result["node"]["id"] == "coffee"
        # coffee 有 incoming: user1 (LIKES), user2 (LIKES), persona1 (KNOWS_ABOUT)
        assert len(result["incoming"]) >= 2

    @pytest.mark.asyncio
    async def test_get_entity_connections_not_found(self, store):
        """测试不存在的实体"""
        result = await store.get_entity_connections("nonexistent")
        assert result["node"] is None

    @pytest.mark.asyncio
    async def test_get_entity_connections_two_hops(self, store):
        """测试两跳连接"""
        await self._build_test_graph(store)

        result = await store.get_entity_connections("user1", max_hops=2)
        related_ids = {r["entity_id"] for r in result["related_entities"]}
        # user1 -> coding -> python (via coding)
        assert "python" in related_ids

    @pytest.mark.asyncio
    async def test_get_knowledge_subgraph(self, store):
        """测试知识子图提取"""
        await self._build_test_graph(store)

        subgraph = await store.get_knowledge_subgraph("user1", depth=1)
        node_ids = {n["id"] for n in subgraph["nodes"]}
        assert "user1" in node_ids
        assert "coffee" in node_ids
        assert subgraph["center_id"] == "user1"
        assert len(subgraph["edges"]) > 0

    @pytest.mark.asyncio
    async def test_get_knowledge_subgraph_max_nodes(self, store):
        """测试子图节点数限制"""
        await self._build_test_graph(store)

        subgraph = await store.get_knowledge_subgraph("user1", depth=2, max_nodes=3)
        assert len(subgraph["nodes"]) <= 3

    @pytest.mark.asyncio
    async def test_find_common_preferences(self, store):
        """测试协同过滤"""
        await self._build_test_graph(store)

        result = await store.find_common_preferences("user1")
        # user1 likes coffee, coding
        assert "coffee" in result["user_likes"]
        assert "coding" in result["user_likes"]
        # user2 also likes coffee
        assert "user2" in result["common"]
        assert "coffee" in result["common"]["user2"]

    @pytest.mark.asyncio
    async def test_find_common_preferences_explicit_users(self, store):
        """测试指定用户列表的协同过滤"""
        await self._build_test_graph(store)

        result = await store.find_common_preferences("user1", ["user2"])
        assert "user2" in result["common"]
        assert "coffee" in result["common"]["user2"]

    @pytest.mark.asyncio
    async def test_find_common_preferences_no_overlap(self, store):
        """测试无重叠的偏好"""
        await store.add_node("u1", "User", {"name": "A"})
        await store.add_node("u2", "User", {"name": "B"})
        await store.add_node("e1", "Entity", {"name": "X"})
        await store.add_node("e2", "Entity", {"name": "Y"})

        await store.add_edge("u1", "e1", "LIKES")
        await store.add_edge("u2", "e2", "LIKES")

        result = await store.find_common_preferences("u1", ["u2"])
        assert result["common"] == {}


class TestGraphStoreWithKuzu:
    """Kuzu 后端测试（如果可用）"""

    @pytest.fixture
    def kuzu_available(self):
        import importlib.util

        return importlib.util.find_spec("kuzu") is not None

    @pytest.mark.asyncio
    async def test_kuzu_init_with_path(self, kuzu_available):
        if not kuzu_available:
            pytest.skip("kuzu not installed")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_kuzu")
            store = GraphStore(db_path=db_path)
            assert store.is_kuzu is True
            await store.close()

    @pytest.mark.asyncio
    async def test_kuzu_init_no_path(self, kuzu_available):
        """没有路径时即使安装了 kuzu 也使用内存模式"""
        if not kuzu_available:
            pytest.skip("kuzu not installed")

        store = GraphStore(db_path=None)
        assert store.is_kuzu is False
        await store.close()

    @pytest.mark.asyncio
    async def test_kuzu_add_and_query(self, kuzu_available):
        if not kuzu_available:
            pytest.skip("kuzu not installed")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_kuzu")
            store = GraphStore(db_path=db_path)

            node_id = await store.add_node("user1", "User", {"name": "TestUser"})
            assert node_id == "user1"

            node = await store.get_node("user1")
            assert node is not None

            await store.close()


class TestGraphStoreKuzuFallback:
    """测试 Kuzu 不可用时的回退行为"""

    @pytest.mark.asyncio
    async def test_fallback_to_memory(self):
        """当 kuzu 未安装时，应自动回退到内存模式；
        当 kuzu 已安装时，应能正常使用 kuzu 后端。"""
        store = GraphStore(db_path="/tmp/nonexistent_kuzu_test")
        # 如果 kuzu 未安装，应该是内存模式
        # 如果 kuzu 已安装，会尝试创建数据库
        # 无论哪种情况都不应报错
        assert isinstance(store.is_kuzu, bool)

        # 两种模式都应该能正常工作
        await store.add_node("test", "User", {"name": "test"})
        node = await store.get_node("test")
        assert node is not None

        await store.close()
