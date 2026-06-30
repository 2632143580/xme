
import warnings
from typing import List, Dict, Optional

from src.config import get_settings

_driver = None


def _get_driver():
    """延迟获取 Neo4j driver（单例复用）。失败时返回 None。"""
    global _driver
    if _driver is not None:
        return _driver
    try:
        from neo4j import GraphDatabase
        s = get_settings()
        driver = GraphDatabase.driver(
            s["neo4j_uri"],
            auth=(s["neo4j_user"], s["neo4j_password"])
        )
        driver.verify_connectivity()
        _driver = driver
        init_schema()
        return driver
    except Exception as e:
        warnings.warn(f"[warn] Neo4j 不可用，图谱功能关闭：{e}")
        return None


def is_connected() -> bool:
    """检查 Neo4j 是否已连接。"""
    return _get_driver() is not None


def close_driver():
    """关闭 Neo4j 连接池。"""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


# ── Schema 初始化 ────────────────────────────────────────────

def init_schema():
    """创建 v5 规定的约束和索引，确保 User 节点有 id 属性。"""
    driver = _get_driver()
    if driver is None:
        return
    try:
        with driver.session() as session:
            session.run("MATCH (u:User) WHERE u.id IS NULL SET u.id = 'user1'")
            session.run("MERGE (u:User {id: 'user1'})")
            for label, prop in [
                ("User", "id"), ("Person", "name"),
                ("Preference", "name"), ("Event", "title")
            ]:
                try:
                    session.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE")
                except Exception:
                    pass
    except Exception as e:
        warnings.warn(f"[warn] 图谱初始化失败：{e}")


# ── 实体写入（v6 schema: 判断 → 分析 → 执行）───────────────

def upsert_preference(name: str, value: str = None, uid: str = "user1") -> str:
    """写入偏好节点，并建立 User-HAS_PREFERENCE 关系。

    四阶段：
    1. 判断：MATCH active 关系
    2. 分析：值相同→unchanged，不同→归档旧值+建新值
    3. 无旧值→created
    4. value=None→archived（软删除）
    返回: created / updated / unchanged / archived / noop
    """
    driver = _get_driver()
    if driver is None:
        return "noop"
    try:
        with driver.session() as session:
            def _tx(tx):
                result = tx.run(
                    "MATCH (u:User {id: $uid})-[r:HAS_PREFERENCE{status:'active'}]"
                    "->(p:Preference {name: $name}) RETURN p.value AS value",
                    uid=uid, name=name)
                record = result.single()
                if record:
                    existing = record["value"]
                    if existing == value:
                        return "unchanged"
                    tx.run(
                        "MATCH (u:User {id: $uid})-[r:HAS_PREFERENCE{status:'active'}]"
                        "->(p:Preference {name: $name}) "
                        "SET r.status = 'archived', r.archived_at = datetime()",
                        uid=uid, name=name)
                    if value is not None:
                        tx.run(
                            "MERGE (p:Preference {name: $name}) "
                            "SET p.value = $value, p.updated_at = datetime() "
                            "WITH p MATCH (u:User {id: $uid}) "
                            "CREATE (u)-[:HAS_PREFERENCE{created_at:datetime(),status:'active'}]->(p)",
                            uid=uid, name=name, value=value)
                        return "updated"
                    return "archived"
                else:
                    if value is not None:
                        tx.run(
                            "MERGE (p:Preference {name: $name}) "
                            "SET p.value = $value, p.created_at = datetime() "
                            "WITH p MATCH (u:User {id: $uid}) "
                            "CREATE (u)-[:HAS_PREFERENCE{created_at:datetime(),status:'active'}]->(p)",
                            uid=uid, name=name, value=value)
                        return "created"
                    return "noop"
            return session.execute_write(_tx)
    except Exception as e:
        warnings.warn(f"[warn] 图谱写入失败（已降级）：{e}")
        return "noop"


def upsert_person(name: str, props: Optional[Dict] = None, uid: str = "user1"):
    """写入/更新人物节点，并建立 User-KNOWS 关系（事务保护）。"""
    driver = _get_driver()
    if driver is None:
        return
    try:
        with driver.session() as session:
            def _tx(tx):
                _props = props or {}
                if _props.get("is_self"):
                    tx.run(
                        "MATCH (u:User {id: $uid}) SET u.name = $name", uid=uid, name=name)
                    tx.run("MERGE (p:Person {name: $name})", name=name)
                    tx.run(
                        "MATCH (u:User {id: $uid}) "
                        "MERGE (p:Person {name: $name}) "
                        "MERGE (u)-[:KNOWS{status:'active',created_at:datetime()}]->(p)", uid=uid, name=name)
                    return
                tx.run(
                    "MERGE (p:Person {name: $name}) SET p += $props",
                    name=name, props=_props)
                tx.run(
                    "MATCH (u:User {id: $uid}) "
                    "MERGE (p:Person {name: $name}) "
                    "MERGE (u)-[:KNOWS{status:'active',created_at:datetime()}]->(p)", uid=uid, name=name)
            session.execute_write(_tx)
    except Exception as e:
        warnings.warn(f"[warn] 图谱写入失败（已降级）：{e}")


def upsert_event(title: str, time: Optional[str] = None, uid: str = "user1"):
    """写入事件节点，并建立 User-EXPERIENCED 关系（事务保护）。"""
    driver = _get_driver()
    if driver is None:
        return
    try:
        with driver.session() as session:
            def _tx(tx):
                props = {"title": title}
                if time:
                    props["time"] = time
                tx.run(
                    "MERGE (e:Event {title: $title}) SET e += $props",
                    title=title, props=props)
                tx.run(
                    "MATCH (u:User {id: $uid}) "
                    "MERGE (e:Event {title: $title}) "
                    "MERGE (u)-[:EXPERIENCED{status:'active',created_at:datetime()}]->(e)", uid=uid, title=title)
            session.execute_write(_tx)
    except Exception as e:
        warnings.warn(f"[warn] 图谱写入失败（已降级）：{e}")


def add_person_relation(person1: str, relation_type: str, person2: str, uid: str = "user1"):
    """写入人物间关系：Person1-[RELATED_TO {type}]->Person2（事务保护）。"""
    driver = _get_driver()
    if driver is None:
        return
    try:
        with driver.session() as session:
            def _tx(tx):
                tx.run(
                    "MERGE (a:Person {name: $p1}) "
                    "MERGE (b:Person {name: $p2}) "
                    "MERGE (a)-[r:RELATED_TO]->(b) "
                    "SET r.type = $rtype, r.updated_at = datetime()",
                    p1=person1, p2=person2, rtype=relation_type)
            session.execute_write(_tx)
    except Exception as e:
        warnings.warn(f"[warn] 关系写入失败（已降级）：{e}")


def soft_delete_entity(name: str, entity_type: str = "person") -> bool:
    """软删除实体：标记 r.status = 'archived'，不物理删除。"""
    driver = _get_driver()
    if driver is None:
        return False
    try:
        with driver.session() as session:
            def _tx(tx):
                type_map = {
                    "person": ("Person", "name"),
                    "preference": ("Preference", "name"),
                    "event": ("Event", "title"),
                }
                info = type_map.get(entity_type)
                if not info:
                    return False
                label, prop = info
                result = tx.run(
                    f"MATCH (u:User)-[r]->(n:{label} {{{prop}: $name}}) "
                    "SET r.status = 'archived', r.archived_at = datetime() "
                    "RETURN COUNT(r) AS cnt", name=name)
                return result.single()["cnt"] > 0
            return session.execute_write(_tx)
    except Exception as e:
        warnings.warn(f"[warn] 软删除失败（已降级）：{e}")
        return False


def delete_entity(name: str, entity_type: str = "person") -> bool:
    """Deprecated: 物理删除（硬删除）。请切换到 soft_delete_entity。"""
    warnings.warn(
        "[deprecated] delete_entity 已改为软删除，请迁移到 soft_delete_entity()",
        DeprecationWarning, stacklevel=2)
    return soft_delete_entity(name, entity_type)


# ── 查询 ────────────────────────────────────────────────────

def query_user_graph(user_id: str = "user1") -> Dict:
    """查询用户的完整图谱：名字、偏好（active）、事件、认识的人。"""
    driver = _get_driver()
    if driver is None:
        return {}
    try:
        with driver.session() as session:
            user_name_result = session.run(
                "MATCH (u:User {id: $uid}) RETURN u.name AS name", uid=user_id)
            user_name = ""
            for r in user_name_result:
                user_name = r.get("name", "") or ""

            preferences = session.run(
                "MATCH (u:User {id: $uid})-[r:HAS_PREFERENCE{status:'active'}]"
                "->(p:Preference) RETURN p.name AS name, p.value AS value",
                uid=user_id)
            events = session.run(
                "MATCH (u:User {id: $uid})-[r:EXPERIENCED{status:'active'}]->(e:Event) "
                "RETURN e.title AS title, e.time AS time", uid=user_id)
            people = session.run(
                "MATCH (u:User {id: $uid})-[r:KNOWS{status:'active'}]->(p:Person) "
                "RETURN p.name AS name", uid=user_id)

            return {
                "user_name": user_name,
                "preferences": [
                    {"name": r["name"], "value": r.get("value", "")}
                    for r in preferences],
                "events": [
                    {"title": r["title"], "time": r.get("time", "")}
                    for r in events],
                "people": [{"name": r["name"]} for r in people],
            }
    except Exception as e:
        warnings.warn(f"[warn] 图谱查询失败（已降级）：{e}")
        return {}
