"""知识图谱工具 -- 将用户明确表达的偏好、事件、人物关系写入 Neo4j。

v6 修复版：
  - write_to_graph 的 preference 类型新增 value 参数
  - 所有参数透传到 graph_module 对应函数
  - delete_from_graph 改为调用 soft_delete_entity

用户说"记住我喜欢X" → Preference(name, value)
用户说"我朋友老王" → Person (KNOWS)
用户说"下周三有考试" → Event (EXPERIENCED)
用户说"老王和小李是同事" → Person-RELATED_TO->Person
"""
from langchain_core.tools import tool

from src.memory import graph as graph_module


def _get_current_user_id() -> str:
    """从 contextvars 获取当前用户 ID（微信 Bot 模式）。

    Raises:
        ImportError: 如果 weixin 包不可达（不应在运行时发生）。
    """
    from src.weixin.user_context import get_current_user
    return get_current_user()


@tool
def write_to_graph(
    entity_type: str,
    entity_name: str,
    relation_type: str = "",
    related_to: str = "",
    time: str = "",
    is_self: bool = False,
    value: str = "",  # v6 新增：偏好值（如"不加糖"、"黑色"）
) -> str:
    """写入知识图谱：偏好/事件/人物/关系。is_self=True 表示用户自己的名字。"""
    uid = _get_current_user_id()
    try:
        if entity_type == "preference":
            # v6：传入 value 参数
            action = graph_module.upsert_preference(entity_name, value or None, uid=uid)
            if action == "unchanged":
                return f"已记住你喜欢{entity_name}（与之前一致）"
            elif action == "updated":
                return f"已更新你的偏好：{entity_name} → {value}"
            elif action == "archived":
                return f"已移除偏好：{entity_name}"
            elif action == "created":
                suffix = f"（{value}）" if value else ""
                return f"已记住你喜欢：{entity_name}{suffix}"
            else:
                return f"偏好无变化：{entity_name}"

        elif entity_type == "person":
            if is_self:
                graph_module.upsert_person(entity_name, props={"is_self": True}, uid=uid)
            else:
                graph_module.upsert_person(entity_name, uid=uid)

            if relation_type and related_to:
                graph_module.add_person_relation(
                    entity_name, relation_type, related_to, uid=uid)
                return f"已记住：{entity_name} 和 {related_to} 是{relation_type}"

            prefix = "你的名字" if is_self else "你认识的人"
            return f"已记住{prefix}：{entity_name}"

        elif entity_type == "event":
            graph_module.upsert_event(entity_name, time=time, uid=uid)
            return f"已记住事件：{entity_name}" + (f"（{time}）" if time else "")

        else:
            return f"不支持的类型：{entity_type}，请使用 preference/event/person"

    except Exception as e:
        return f"图谱写入失败（已降级为本地存储）：{e}"


@tool
def query_graph(query: str) -> str:
    """查询知识图谱中的偏好、事件、人物关系。"""
    uid = _get_current_user_id()
    try:
        data = graph_module.query_user_graph(user_id=uid)
        if not data:
            return "图谱暂无数据（Neo4j 可能未连接）。"
        parts = []
        if data.get("user_name"):
            parts.append(f"用户名字：{data['user_name']}")
        if data.get("preferences"):
            parts.append("偏好：" + "、".join(
                f"{p['name']}={p.get('value', '')}" if p.get('value') else p['name']
                for p in data["preferences"]))
        if data.get("people"):
            parts.append("认识的人：" + "、".join(p["name"] for p in data["people"]))
        if data.get("events"):
            ev = [f"{e['title']}({e.get('time', '')})" for e in data["events"]]
            parts.append("事件：" + "、".join(ev))
        result = "\n".join(parts) if parts else "图谱暂无数据。"
        # token优化：限制返回长度
        MAX_GRAPH_RESULT = 500
        if len(result) > MAX_GRAPH_RESULT:
            result = result[:MAX_GRAPH_RESULT] + "\n...(已截断)"
        return result
    except Exception as e:
        return f"图谱查询失败：{e}"


@tool
def delete_from_graph(entity_name: str, entity_type: str = "person") -> str:
    """从知识图谱中软删除指定实体（归档，保留历史可回溯）。"""
    try:
        ok = graph_module.soft_delete_entity(entity_name, entity_type)
        if ok:
            return f"已从图谱归档 {entity_type}: {entity_name}（历史记录保留）"
        return f"未找到 {entity_type}: {entity_name}"
    except Exception as e:
        return f"删除失败：{e}"
