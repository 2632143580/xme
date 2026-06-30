"""工具函数--create_note / retrieve_memory / delete_note / update_note / list_notes。"""
from functools import lru_cache
from langchain_core.tools import tool

from src.memory.client import MemoryClient


@lru_cache(maxsize=1)
def get_client() -> "MemoryClient":
    """单例 MemoryClient（延迟初始化）。"""
    return MemoryClient()


def _get_current_user_id() -> str:
    """从 contextvars 获取当前用户 ID（微信 Bot 模式）。

    Raises:
        ImportError: 如果 weixin 包不可达（不应在运行时发生）。
    """
    from src.weixin.user_context import get_current_user
    return get_current_user()


@tool
def create_note(content: str) -> str:
    """记录笔记、日记或待办事项。"""
    client = get_client()
    title = (content.split("\n")[0][:20]) or "无标题"
    user_id = _get_current_user_id()
    note_id = client.save_note(title, content, source_user_id=user_id)
    return f"已记录笔记（ID:{note_id}）。"


@tool
def list_notes(limit: int = 10) -> str:
    """列出笔记列表（含ID）。"""
    client = get_client()
    rows = client.list_notes(limit)
    if not rows:
        return "当前没有任何笔记。"
    result = ["现有笔记列表："]
    for r in rows:
        content = r["content"]
        summary = content[:30] + "…" if len(content) > 30 else content
        result.append(f"  ID:{r['id']} - {r['title']}: {summary}")
    return "\n".join(result)


@tool
def delete_note(note_id: int) -> str:
    """删除笔记。先调 list_notes 查 ID。"""
    client = get_client()
    ok = client.delete_note(note_id)
    return f"已删除笔记（ID:{note_id}）" if ok else f"未找到笔记（ID:{note_id}）"


@tool
def update_note(note_id: int, content: str) -> str:
    """修改笔记内容。先调 list_notes 查 ID。"""
    client = get_client()
    title = (content.split("\n")[0][:20]) or "无标题"
    ok = client.update_note(note_id, title, content)
    return f"已更新笔记（ID:{note_id}）" if ok else f"未找到笔记（ID:{note_id}）"


@tool
def retrieve_memory(query: str) -> str:
    """回忆用户过去说过的话、记过的笔记或对话摘要。
    当用户问"我是谁/你记得我吗/你知道我叫什么"时也会调用此工具查找身份信息。"""
    client = get_client()

    # 优先向量检索
    results = client.full_text_search(query, limit=5)

    # 同时查询知识图谱（偏好/事件/认识的人/用户名字）
    graph_info = ""
    try:
        from src.memory.graph import query_user_graph
        graph_data = query_user_graph(user_id=_get_current_user_id())
        if graph_data:
            parts = []
            if graph_data.get("user_name"):
                parts.append(f"用户名字: {graph_data['user_name']}")
            if graph_data.get("preferences"):
                pref_strs = []
                for p in graph_data["preferences"]:
                    name = p["name"]
                    value = p.get("value", "")
                    pref_strs.append(f"{name}={value}" if value else name)
                parts.append("用户偏好: " + ", ".join(pref_strs))
            if graph_data.get("people"):
                parts.append("用户认识的人: " + ", ".join(graph_data["people"]))
            if graph_data.get("events"):
                events_str = ", ".join(
                    f"{e['title']}({e.get('time', '')})" for e in graph_data["events"]
                )
                parts.append("用户经历的事件: " + events_str)
            if parts:
                graph_info = "【知识图谱】\n" + "\n".join(parts)
    except Exception:
        pass  # 图谱查询失败不阻断主流程

    if not results and not graph_info:
        recent = client.recent_dialogue(limit=5)
        if recent:
            return "最近对话：\n" + "\n".join(
                f"[{d['created_at']}] {d['role']}：{d['content']}"
                for d in recent
            )
        return "还没有任何历史记录。"

    # 格式化文本检索结果
    text_parts = []
    for r in results:
        if "title" in r:  # 笔记
            text_parts.append(f"笔记：{r.get('title', '')}：{r.get('content', '')}")
        else:  # 对话
            text_parts.append(f"对话：{r.get('role', '')}：{r.get('content', '')}")

    combined = ""
    if text_parts:
        combined += "【检索结果】\n" + "\n".join(text_parts)
    if graph_info:
        combined += "\n" + graph_info

    MAX_RESULT_LENGTH = 800  # token优化：防止检索结果过大
    if len(combined) > MAX_RESULT_LENGTH:
        combined = combined[:MAX_RESULT_LENGTH] + "\n...(结果已截断)"
    return combined
