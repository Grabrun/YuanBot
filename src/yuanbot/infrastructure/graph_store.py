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
        props_str = ", ".join(
            f"{k}: '{self._escape(str(v))}'" for k, v in all_props.items()
        )

        try:
            self._conn.execute(
                f"CREATE (n:{node_type} {{{props_str}}})"
            )
        except RuntimeError:
            # 主键冲突 -> 使用 MATCH + SET 更新
            set_parts = []
            for k, v in prop_map.items():
                set_parts.append(f"n.{k} = '{self._escape(str(v))}'")
            set_clause = ", ".join(set_parts)
            try:
                self._conn.execute(
                    f"MATCH (n:{node_type}) WHERE n.id = '{self._escape(node_id)}' "
                    f"SET {set_clause}"
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

        for edge_id, edge in self._memory_graph.edges.items():
            matched = False
            if direction in ("outgoing", "both") and edge["source"] == node_id:
                if edge_type is None or edge["type"] == edge_type:
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

            if direction in ("incoming", "both") and edge["target"] == node_id:
                if edge_type is None or edge["type"] == edge_type:
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

    @staticmethod
    def _escape(value: str) -> str:
        """转义字符串中的单引号"""
        return value.replace("'", "\\'")
