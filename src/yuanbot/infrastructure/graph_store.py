"""知识图谱存储 - 使用 Kuzu 嵌入式图数据库

用于语义记忆层，存储实体和关系：
- 节点：User, Entity, Event, Trait, SemanticMemory
- 关系：LIKES, DISLIKES, HAS_TRAIT, EXPERIENCED, ASSOCIATED_WITH, HAS_MEMORY
"""

from __future__ import annotations

import importlib.util
import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 检测 kuzu 是否可用
_HAS_KUZU = importlib.util.find_spec("kuzu") is not None


def is_kuzu_available() -> bool:
    """检测 kuzu 是否已安装"""
    return _HAS_KUZU


# Kuzu 节点表定义
_NODE_TABLES = {
    "User": {"name": "STRING", "properties": "STRING"},
    "AIPersona": {"name": "STRING", "properties": "STRING"},
    "Entity": {"name": "STRING", "type": "STRING", "properties": "STRING"},
    "Event": {"name": "STRING", "timestamp": "STRING", "properties": "STRING"},
    "Trait": {"name": "STRING", "value": "STRING", "properties": "STRING"},
    "SemanticMemory": {
        "content": "STRING",
        "relation_type": "STRING",
        "properties": "STRING",
    },
}

# Kuzu 关系表定义 (source_table, target_table, properties)
_REL_TABLES = {
    "LIKES": ("User", "Entity", {"weight": "DOUBLE"}),
    "DISLIKES": ("User", "Entity", {"weight": "DOUBLE"}),
    "HAS_TRAIT": ("User", "Trait", {}),
    "EXPERIENCED": ("User", "Event", {}),
    "ASSOCIATED_WITH": ("Entity", "Entity", {"strength": "DOUBLE"}),
    "HAS_MEMORY": ("User", "SemanticMemory", {}),
    "IN_RELATIONSHIP_WITH": ("User", "AIPersona", {"stage": "STRING", "since": "STRING"}),
    "KNOWS_ABOUT": ("AIPersona", "Entity", {}),
}


class InMemoryGraph:
    """内存图存储，当 Kuzu 不可用时作为回退方案"""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}  # node_id -> {type, properties}
        self.edges: dict[str, dict[str, Any]] = {}  # edge_id -> {source, target, type, properties}


class GraphStore:
    """知识图谱存储

    由于 Kuzu 可能未安装，提供内存图存储作为回退。
    """

    def __init__(self, db_path: str | None = None):
        self._use_kuzu = False
        self._memory_graph = InMemoryGraph()
        self._db: Any = None
        self._conn: Any = None
        self._db_path = db_path
        self._try_init_kuzu(db_path)

    @property
    def is_kuzu(self) -> bool:
        """是否使用 Kuzu 后端"""
        return self._use_kuzu

    @property
    def backend(self) -> str:
        """当前使用的后端名称"""
        if self._use_kuzu:
            return "kuzu"
        return "memory"

    def _try_init_kuzu(self, db_path: str | None) -> None:
        """尝试初始化 Kuzu，失败则使用内存图"""
        if not _HAS_KUZU:
            logger.info("kuzu_not_available, using in-memory graph")
            return

        if not db_path:
            logger.info("kuzu_no_path, using in-memory graph")
            return

        try:
            import kuzu  # type: ignore[import-untyped]

            self._db = kuzu.Database(db_path)
            self._conn = kuzu.Connection(self._db)
            self._init_schema()
            self._use_kuzu = True
            logger.info("kuzu_initialized", path=db_path)
        except Exception as e:
            logger.warning("kuzu_init_failed_fallback_memory", error=str(e))

    def _init_schema(self) -> None:
        """初始化 Kuzu Schema - 创建节点表和关系表"""
        assert self._conn is not None

        # 创建节点表
        for table_name, columns in _NODE_TABLES.items():
            col_defs = ", ".join(f"{col} {dtype}" for col, dtype in columns.items())
            try:
                self._conn.execute(
                    f"CREATE NODE TABLE IF NOT EXISTS {table_name}("
                    f"id STRING, {col_defs}, PRIMARY KEY(id))"
                )
            except Exception as e:
                logger.debug("kuzu_node_table_exists", table=table_name, error=str(e))

        # 创建关系表
        for rel_name, (src, dst, props) in _REL_TABLES.items():
            prop_defs = ""
            if props:
                prop_defs = ", " + ", ".join(f"{col} {dtype}" for col, dtype in props.items())
            try:
                self._conn.execute(
                    f"CREATE REL TABLE IF NOT EXISTS {rel_name}(FROM {src} TO {dst}{prop_defs})"
                )
            except Exception as e:
                logger.debug("kuzu_rel_table_exists", table=rel_name, error=str(e))

    async def add_node(
        self,
        node_id: str,
        node_type: str,
        properties: dict[str, Any],
    ) -> str:
        """添加节点

        Args:
            node_id: 节点 ID（为空则自动生成）
            node_type: 节点类型（User, Entity, Event, Trait, SemanticMemory）
            properties: 节点属性

        Returns:
            节点 ID
        """
        if not node_id:
            node_id = str(uuid.uuid4())

        if self._use_kuzu:
            await self._kuzu_add_node(node_id, node_type, properties)
        else:
            self._memory_graph.nodes[node_id] = {
                "type": node_type,
                "properties": properties,
            }

        logger.debug("graph_node_added", node_id=node_id, node_type=node_type)
        return node_id

    async def _kuzu_add_node(
        self, node_id: str, node_type: str, properties: dict[str, Any]
    ) -> None:
        """通过 Kuzu 添加节点

        使用 CREATE 语句插入新节点，如果主键冲突则使用 MATCH+SET 更新。
        """
        assert self._conn is not None

        table_def = _NODE_TABLES.get(node_type)
        if table_def is None:
            raise ValueError(f"Unknown node type: {node_type}")

        # 构建属性字典
        prop_map: dict[str, str] = {}
        for col in table_def:
            if col == "properties":
                extra = {k: v for k, v in properties.items() if k not in table_def}
                import json

                prop_map[col] = json.dumps(extra) if extra else "{}"
            else:
                prop_map[col] = str(properties.get(col, ""))

        # 构建 CREATE 子句: CREATE (n:Type {id: '...', col1: '...', col2: '...'})
        all_props = {"id": node_id, **prop_map}
        props_str = ", ".join(f"{k}: '{self._escape(str(v))}'" for k, v in all_props.items())

        try:
            self._conn.execute(f"CREATE (n:{node_type} {{{props_str}}})")
        except RuntimeError:
            # 主键冲突 -> 使用 MATCH + SET 更新
            set_parts = []
            for k, v in prop_map.items():
                set_parts.append(f"n.{k} = '{self._escape(str(v))}'")
            set_clause = ", ".join(set_parts)
            try:
                self._conn.execute(
                    f"MATCH (n:{node_type}) WHERE n.id = '{self._escape(node_id)}' SET {set_clause}"
                )
            except Exception as e:
                logger.warning("kuzu_add_node_update_failed", node_id=node_id, error=str(e))
        except Exception as e:
            logger.warning("kuzu_add_node_failed", node_id=node_id, error=str(e))

    async def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """添加关系边

        Args:
            source_id: 源节点 ID
            target_id: 目标节点 ID
            edge_type: 关系类型
            properties: 关系属性

        Returns:
            边 ID
        """
        edge_id = str(uuid.uuid4())
        props = properties or {}

        if self._use_kuzu:
            await self._kuzu_add_edge(source_id, target_id, edge_type, props)
        else:
            self._memory_graph.edges[edge_id] = {
                "source": source_id,
                "target": target_id,
                "type": edge_type,
                "properties": props,
            }

        logger.debug(
            "graph_edge_added",
            edge_id=edge_id,
            source=source_id,
            target=target_id,
            edge_type=edge_type,
        )
        return edge_id

    async def _kuzu_add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        properties: dict[str, Any],
    ) -> None:
        """通过 Kuzu 添加关系边"""
        assert self._conn is not None

        table_def = _REL_TABLES.get(edge_type)
        if table_def is None:
            raise ValueError(f"Unknown edge type: {edge_type}")

        src_table, dst_table, prop_types = table_def

        prop_parts = []
        for col, dtype in prop_types.items():
            val = properties.get(col, 0.0 if dtype == "DOUBLE" else "")
            prop_parts.append(f"{col}: {val}")

        set_clause = ""
        if prop_parts:
            set_clause = " SET " + ", ".join(
                f"r.{p.split(':')[0].strip()} = {p.split(':')[1].strip()}" for p in prop_parts
            )

        try:
            self._conn.execute(
                f"MATCH (a:{src_table}), (b:{dst_table}) "
                f"WHERE a.id = '{self._escape(source_id)}' AND b.id = '{self._escape(target_id)}' "
                f"CREATE (a)-[r:{edge_type}]->(b){set_clause}"
            )
        except Exception as e:
            logger.warning("kuzu_add_edge_failed", error=str(e))

    async def get_neighbors(
        self,
        node_id: str,
        edge_type: str | None = None,
        direction: str = "outgoing",
    ) -> list[dict[str, Any]]:
        """获取邻居节点

        Args:
            node_id: 节点 ID
            edge_type: 关系类型过滤（可选）
            direction: 方向 - "outgoing", "incoming", "both"

        Returns:
            邻居节点列表
        """
        if self._use_kuzu:
            return await self._kuzu_get_neighbors(node_id, edge_type, direction)
        return self._memory_get_neighbors(node_id, edge_type, direction)

    def _memory_get_neighbors(
        self,
        node_id: str,
        edge_type: str | None,
        direction: str,
    ) -> list[dict[str, Any]]:
        """内存模式获取邻居"""
        neighbors: list[dict[str, Any]] = []

        for edge in self._memory_graph.edges.values():
            matched = False
            if (
                direction in ("outgoing", "both")
                and edge["source"] == node_id
                and (edge_type is None or edge["type"] == edge_type)
            ):
                target = self._memory_graph.nodes.get(edge["target"])
                if target:
                    neighbors.append(
                        {
                            "node_id": edge["target"],
                            "node_type": target["type"],
                            "properties": target["properties"],
                            "edge_type": edge["type"],
                            "edge_properties": edge["properties"],
                            "direction": "outgoing",
                        }
                    )
                    matched = True

            if (
                direction in ("incoming", "both")
                and edge["target"] == node_id
                and (edge_type is None or edge["type"] == edge_type)
            ):
                source = self._memory_graph.nodes.get(edge["source"])
                if source and not matched:
                    neighbors.append(
                        {
                            "node_id": edge["source"],
                            "node_type": source["type"],
                            "properties": source["properties"],
                            "edge_type": edge["type"],
                            "edge_properties": edge["properties"],
                            "direction": "incoming",
                        }
                    )

        return neighbors

    async def _kuzu_get_neighbors(
        self,
        node_id: str,
        edge_type: str | None,
        direction: str,
    ) -> list[dict[str, Any]]:
        """Kuzu 模式获取邻居"""
        assert self._conn is not None
        neighbors: list[dict[str, Any]] = []

        if direction in ("outgoing", "both"):
            rel_filter = f":{edge_type}" if edge_type else ""
            try:
                result = self._conn.execute(
                    f"MATCH (a)-[r{rel_filter}]->(b) "
                    f"WHERE a.id = '{self._escape(node_id)}' "
                    f"RETURN b.id, b.name, type(r), b.properties"
                )
                while result.has_next():
                    row = result.get_next()
                    neighbors.append(
                        {
                            "node_id": row[0],
                            "node_type": "unknown",
                            "properties": {"name": row[1]},
                            "edge_type": row[2],
                            "edge_properties": {},
                            "direction": "outgoing",
                        }
                    )
            except Exception as e:
                logger.debug("kuzu_get_neighbors_outgoing_failed", error=str(e))

        if direction in ("incoming", "both"):
            rel_filter = f":{edge_type}" if edge_type else ""
            try:
                result = self._conn.execute(
                    f"MATCH (a)<-[r{rel_filter}]-(b) "
                    f"WHERE a.id = '{self._escape(node_id)}' "
                    f"RETURN b.id, b.name, type(r), b.properties"
                )
                while result.has_next():
                    row = result.get_next()
                    neighbors.append(
                        {
                            "node_id": row[0],
                            "node_type": "unknown",
                            "properties": {"name": row[1]},
                            "edge_type": row[2],
                            "edge_properties": {},
                            "direction": "incoming",
                        }
                    )
            except Exception as e:
                logger.debug("kuzu_get_neighbors_incoming_failed", error=str(e))

        return neighbors

    async def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 3,
    ) -> list[list[str]]:
        """查找两个节点之间的路径

        Args:
            source_id: 起始节点 ID
            target_id: 目标节点 ID
            max_depth: 最大搜索深度

        Returns:
            路径列表，每条路径为节点 ID 列表
        """
        if self._use_kuzu:
            return await self._kuzu_find_path(source_id, target_id, max_depth)
        return self._memory_find_path(source_id, target_id, max_depth)

    def _memory_find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int,
    ) -> list[list[str]]:
        """内存模式 BFS 寻路"""
        if source_id == target_id:
            return [[source_id]]

        # 构建邻接表（双向）
        adj: dict[str, list[str]] = {}
        for edge in self._memory_graph.edges.values():
            src, tgt = edge["source"], edge["target"]
            adj.setdefault(src, []).append(tgt)
            adj.setdefault(tgt, []).append(src)

        # BFS 寻找所有最短路径
        # path 长度 = 节点数，边数 = len(path) - 1
        visited: dict[str, int] = {source_id: 0}
        queue: list[tuple[str, list[str]]] = [(source_id, [source_id])]
        found_paths: list[list[str]] = []
        min_edge_count = max_depth + 1

        while queue:
            current, path = queue.pop(0)
            edge_count = len(path) - 1

            if edge_count > min_edge_count:
                continue

            if current == target_id and edge_count <= min_edge_count:
                min_edge_count = edge_count
                found_paths.append(path)
                continue

            if edge_count >= max_depth:
                continue

            for neighbor in adj.get(current, []):
                new_edge_count = len(path)  # len(path) - 1 + 1
                if neighbor not in visited or visited[neighbor] >= new_edge_count:
                    visited[neighbor] = new_edge_count
                    queue.append((neighbor, path + [neighbor]))

        return found_paths

    async def _kuzu_find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int,
    ) -> list[list[str]]:
        """Kuzu 模式寻路"""
        assert self._conn is not None
        paths: list[list[str]] = []

        try:
            result = self._conn.execute(
                f"MATCH (a)-[r*1..{max_depth}]->(b) "
                f"WHERE a.id = '{self._escape(source_id)}' AND b.id = '{self._escape(target_id)}' "
                f"RETURN nodes(r) LIMIT 10"
            )
            while result.has_next():
                row = result.get_next()
                # row[0] 是路径中的节点列表
                if isinstance(row[0], list):
                    paths.append([str(n) for n in row[0]])
                else:
                    paths.append([source_id, target_id])
        except Exception as e:
            logger.debug("kuzu_find_path_failed", error=str(e))
            # 回退到内存模式
            return self._memory_find_path(source_id, target_id, max_depth)

        return paths

    async def get_user_relationships(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        """获取用户的所有关系

        Args:
            user_id: 用户节点 ID

        Returns:
            按关系类型分组的邻居节点
        """
        neighbors = await self.get_neighbors(user_id, direction="outgoing")

        relationships: dict[str, list[dict[str, Any]]] = {}
        for neighbor in neighbors:
            rel_type = neighbor.get("edge_type", "unknown")
            if rel_type not in relationships:
                relationships[rel_type] = []
            relationships[rel_type].append(
                {
                    "node_id": neighbor["node_id"],
                    "node_type": neighbor.get("node_type", "unknown"),
                    "properties": neighbor.get("properties", {}),
                    "edge_properties": neighbor.get("edge_properties", {}),
                }
            )

        return relationships

    async def update_relationship(
        self,
        edge_id: str,
        properties: dict[str, Any],
    ) -> bool:
        """更新关系属性

        Args:
            edge_id: 边 ID
            properties: 要更新的属性

        Returns:
            是否更新成功
        """
        if self._use_kuzu:
            # Kuzu 模式下边 ID 是虚拟的，无法直接更新
            logger.warning("kuzu_update_relationship_not_supported", edge_id=edge_id)
            return False

        edge = self._memory_graph.edges.get(edge_id)
        if not edge:
            return False

        edge["properties"].update(properties)
        logger.debug("graph_edge_updated", edge_id=edge_id)
        return True

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        """获取单个节点

        Args:
            node_id: 节点 ID

        Returns:
            节点信息，不存在返回 None
        """
        if self._use_kuzu:
            assert self._conn is not None
            for table_name in _NODE_TABLES:
                try:
                    result = self._conn.execute(
                        f"MATCH (a:{table_name}) WHERE a.id = '{self._escape(node_id)}' "
                        f"RETURN a.id, a.name, a.properties"
                    )
                    if result.has_next():
                        row = result.get_next()
                        return {
                            "id": row[0],
                            "type": table_name,
                            "properties": {"name": row[1]},
                        }
                except Exception:
                    continue
            return None

        node = self._memory_graph.nodes.get(node_id)
        if node is None:
            return None
        return {"id": node_id, "type": node["type"], "properties": node["properties"]}

    async def remove_node(self, node_id: str) -> bool:
        """删除节点及其关联边

        Args:
            node_id: 节点 ID

        Returns:
            是否删除成功
        """
        if self._use_kuzu:
            assert self._conn is not None
            try:
                self._conn.execute(f"MATCH (a) WHERE a.id = '{self._escape(node_id)}' DELETE a")
                return True
            except Exception as e:
                logger.warning("kuzu_remove_node_failed", node_id=node_id, error=str(e))
                return False

        if node_id not in self._memory_graph.nodes:
            return False

        del self._memory_graph.nodes[node_id]

        # 删除关联边
        edges_to_remove = [
            eid
            for eid, edge in self._memory_graph.edges.items()
            if edge["source"] == node_id or edge["target"] == node_id
        ]
        for eid in edges_to_remove:
            del self._memory_graph.edges[eid]

        return True

    async def remove_edge(self, edge_id: str) -> bool:
        """删除关系边

        Args:
            edge_id: 边 ID

        Returns:
            是否删除成功
        """
        if self._use_kuzu:
            logger.warning("kuzu_remove_edge_not_supported", edge_id=edge_id)
            return False

        if edge_id not in self._memory_graph.edges:
            return False

        del self._memory_graph.edges[edge_id]
        return True

    async def get_all_nodes(self, node_type: str | None = None) -> list[dict[str, Any]]:
        """获取所有节点

        Args:
            node_type: 节点类型过滤（可选）

        Returns:
            节点列表
        """
        if self._use_kuzu:
            assert self._conn is not None
            nodes: list[dict[str, Any]] = []
            tables = [node_type] if node_type else list(_NODE_TABLES.keys())
            for table_name in tables:
                try:
                    result = self._conn.execute(
                        f"MATCH (a:{table_name}) RETURN a.id, a.name, a.properties"
                    )
                    while result.has_next():
                        row = result.get_next()
                        nodes.append(
                            {
                                "id": row[0],
                                "type": table_name,
                                "properties": {"name": row[1]},
                            }
                        )
                except Exception:
                    continue
            return nodes

        nodes = []
        for nid, node in self._memory_graph.nodes.items():
            if node_type is None or node["type"] == node_type:
                nodes.append({"id": nid, "type": node["type"], "properties": node["properties"]})
        return nodes

    async def close(self) -> None:
        """关闭连接"""
        if self._use_kuzu:
            self._conn = None
            self._db = None
            self._use_kuzu = False
            logger.info("kuzu_connection_closed")
        else:
            self._memory_graph = InMemoryGraph()
            logger.info("in_memory_graph_cleared")

    # ------------------------------------------------------------------
    # 图推理方法 (Graph Reasoning)
    # ------------------------------------------------------------------

    async def find_related_entities(
        self,
        user_id: str,
        min_weight: float = 0.0,
        relation_types: list[str] | None = None,
        max_depth: int = 2,
    ) -> list[dict[str, Any]]:
        """查找与用户相关的实体（多跳推理）

        从用户出发，沿 LIKES/DISLIKES/EXPERIENCED 等关系遍历图谱，
        收集所有可达实体及其关联关系。支持按权重过滤和深度限制。

        Args:
            user_id: 用户节点 ID
            min_weight: 最小关系权重过滤（仅对有 weight 属性的关系有效）
            relation_types: 限制遍历的关系类型（默认 LIKES/DISLIKES/ASSOCIATED_WITH）
            max_depth: 最大遍历深度

        Returns:
            相关实体列表，每个元素包含 entity_id, entity_type, properties,
            path（从用户到该实体的路径）, relation_chain（经过的关系类型链）
        """
        rels = relation_types or ["LIKES", "DISLIKES", "ASSOCIATED_WITH"]
        visited: dict[str, int] = {user_id: 0}
        queue: list[tuple[str, list[str], list[str]]] = [(user_id, [user_id], [])]
        results: list[dict[str, Any]] = []

        while queue:
            current_id, path, rel_chain = queue.pop(0)
            depth = len(path) - 1

            if depth >= max_depth:
                continue

            for rel_type in rels:
                neighbors = await self.get_neighbors(
                    current_id, edge_type=rel_type, direction="outgoing"
                )
                for neighbor in neighbors:
                    nid = neighbor["node_id"]
                    new_depth = depth + 1

                    # 权重过滤
                    edge_props = neighbor.get("edge_properties", {})
                    weight = edge_props.get("weight", 1.0)
                    if weight < min_weight:
                        continue

                    # 收集实体结果（排除 User 和 Trait 节点本身）
                    n_type = neighbor.get("node_type", "unknown")
                    if n_type not in ("User", "Trait"):
                        results.append(
                            {
                                "entity_id": nid,
                                "entity_type": n_type,
                                "properties": neighbor.get("properties", {}),
                                "path": path + [nid],
                                "relation_chain": rel_chain + [rel_type],
                                "depth": new_depth,
                            }
                        )

                    # 继续遍历（避免循环）
                    if nid not in visited or visited[nid] > new_depth:
                        visited[nid] = new_depth
                        queue.append((nid, path + [nid], rel_chain + [rel_type]))

        return results

    async def get_entity_connections(
        self,
        entity_id: str,
        max_hops: int = 1,
    ) -> dict[str, Any]:
        """获取实体的所有连接关系

        返回实体的一跳或多跳邻居及其关系信息，用于构建用户画像
        或回答 "用户喜欢什么" 类型的查询。

        Args:
            entity_id: 实体节点 ID
            max_hops: 最大跳数

        Returns:
            包含 node（节点信息）, outgoing（出边关系）, incoming（入边关系）,
            related_entities（多跳相关实体）的字典
        """
        node = await self.get_node(entity_id)
        if not node:
            return {"node": None, "outgoing": [], "incoming": [], "related_entities": []}

        outgoing = await self.get_neighbors(entity_id, direction="outgoing")
        incoming = await self.get_neighbors(entity_id, direction="incoming")

        related_entities: list[dict[str, Any]] = []
        if max_hops >= 2:
            for neighbor in outgoing + incoming:
                nid = neighbor["node_id"]
                second_hop = await self.get_neighbors(nid, direction="both")
                related_entities.extend(
                    {
                        "entity_id": n2["node_id"],
                        "entity_type": n2.get("node_type", "unknown"),
                        "properties": n2.get("properties", {}),
                        "via": nid,
                        "via_relation": neighbor.get("edge_type", ""),
                    }
                    for n2 in second_hop
                    if n2["node_id"] != entity_id
                )

        return {
            "node": node,
            "outgoing": outgoing,
            "incoming": incoming,
            "related_entities": related_entities,
        }

    async def get_knowledge_subgraph(
        self,
        center_id: str,
        depth: int = 2,
        max_nodes: int = 50,
    ) -> dict[str, Any]:
        """获取以某节点为中心的知识子图

        用于构建上下文信息或可视化。返回节点和边的集合，
        适合注入到 LLM 的 system prompt 中作为背景知识。

        Args:
            center_id: 中心节点 ID
            depth: 子图半径（最大跳数）
            max_nodes: 最大节点数（防止过大子图）

        Returns:
            {nodes: [...], edges: [...], center_id: str}
        """
        visited: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        queue: list[tuple[str, int]] = [(center_id, 0)]

        while queue and len(visited) < max_nodes:
            node_id, d = queue.pop(0)
            if node_id in visited or d > depth:
                continue

            node = await self.get_node(node_id)
            if node:
                visited[node_id] = node

            if d < depth:
                neighbors = await self.get_neighbors(node_id, direction="both")
                for neighbor in neighbors:
                    nid = neighbor["node_id"]
                    # 记录边
                    edge_info = {
                        "source": node_id if neighbor["direction"] == "outgoing" else nid,
                        "target": nid if neighbor["direction"] == "outgoing" else node_id,
                        "type": neighbor.get("edge_type", "unknown"),
                        "properties": neighbor.get("edge_properties", {}),
                    }
                    if edge_info not in edges:
                        edges.append(edge_info)

                    if nid not in visited:
                        queue.append((nid, d + 1))

        return {
            "center_id": center_id,
            "nodes": list(visited.values()),
            "edges": edges,
        }

    async def find_common_preferences(
        self,
        user_id: str,
        other_user_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """查找用户间的共同偏好（协同过滤）

        找出指定用户与其他用户共同 LIKES 的实体，用于推荐系统。
        如果不指定 other_user_ids，则自动发现所有有 LIKES 关系的用户。

        Args:
            user_id: 目标用户 ID
            other_user_ids: 要比较的其他用户 ID 列表（可选）

        Returns:
            {user_likes: [...], common: {other_user: [shared_entities]}}
        """
        # 获取目标用户的偏好
        user_likes_neighbors = await self.get_neighbors(
            user_id, edge_type="LIKES", direction="outgoing"
        )
        user_likes = {n["node_id"] for n in user_likes_neighbors}

        # 如果没有指定其他用户，自动发现
        if other_user_ids is None:
            all_users = await self.get_all_nodes(node_type="User")
            other_user_ids = [u["id"] for u in all_users if u["id"] != user_id]

        common: dict[str, list[str]] = {}
        for other_id in other_user_ids:
            other_likes_neighbors = await self.get_neighbors(
                other_id, edge_type="LIKES", direction="outgoing"
            )
            other_likes = {n["node_id"] for n in other_likes_neighbors}
            shared = user_likes & other_likes
            if shared:
                common[other_id] = list(shared)

        return {
            "user_likes": list(user_likes),
            "common": common,
        }

    @staticmethod
    def _escape(value: str) -> str:
        """转义字符串中的单引号"""
        return value.replace("'", "\\'")
