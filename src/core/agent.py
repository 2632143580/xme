"""LangGraph Agent 核心 -- Agentic RAG 架构：自主决策 + 自修正循环。

架构:
  agent → should_continue → [tools, evaluate]
  tools → agent
  evaluate → route_after_evaluate → [agent (retry), __end__]

不再使用硬编码关键词规则，Agent 自主判断何时调用工具。
evaluate 节点负责自修正：检查回复质量，不够好则重试。

LLM 实例延迟加载：每次对话从 env 读取最新配置，支持热切换模型。
"""
import os
import sqlite3
from datetime import datetime
from typing import TypedDict, Annotated, Sequence
import operator

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage)

from src.tools.note_tools import create_note, retrieve_memory, delete_note, update_note, list_notes, get_client
from src.tools.graph_tools import write_to_graph, query_graph, delete_from_graph
from src.memory.prompts import SYSTEM_PROMPT, EVALUATE_PROMPT

MAX_WINDOW = 20  # token 优化：从 40 降至 20
TOOL_MSG_MAX_LEN = 300  # ToolMessage 截断上限
MAX_RETRIES = 2


def _trim(messages):
    """滑动窗口：保留最近 MAX_WINDOW 条消息，ToolMessage 截断到 300 字符。"""
    msgs = list(messages)
    # 对所有 ToolMessage 做截断
    for i, m in enumerate(msgs):
        if isinstance(m, ToolMessage) and m.content and len(m.content) > TOOL_MSG_MAX_LEN:
            msgs[i] = ToolMessage(
                content=m.content[:TOOL_MSG_MAX_LEN] + "...(已截断)",
                name=m.name, tool_call_id=m.tool_call_id,
            )
    if len(msgs) <= MAX_WINDOW:
        return msgs
    window = msgs[-MAX_WINDOW:]
    cut = len(msgs) - MAX_WINDOW
    while window and isinstance(window[0], ToolMessage):
        if cut - 1 < 0:
            break
        window.insert(0, msgs[cut - 1])
        cut -= 1
    return window


def _last_human_content(messages):
    """找最后一条 HumanMessage 的内容。"""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return m.content
    return None


def _tools_have_been_called(messages) -> bool:
    """检查是否有 ToolMessage（工具已被调用过）。"""
    return any(isinstance(m, ToolMessage) for m in messages)


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    retry_count: int  # evaluate 自修正重试计数


# ── 工具列表（不变，无需热更新）─────────────────────────────────

tools = [create_note, retrieve_memory, delete_note, update_note, list_notes,
         write_to_graph, query_graph, delete_from_graph]


# ── LLM 延迟加载（每次对话从 env 读取最新配置）───────────────────

def _get_llm_with_tools():
    """返回带工具的 LLM。每次调用从 get_llm() 读取最新 .env 配置。"""
    from src.llm_factory import get_llm
    llm = get_llm(temperature=0.5, timeout=30)  # token优化：0.7→0.5
    return llm.bind_tools(tools)


def _get_eval_llm():
    """返回评估用 LLM。每次调用从 get_llm() 读取最新配置。"""
    from src.llm_factory import get_llm
    return get_llm(temperature=0, timeout=15)


# ── agent 节点 ───────────────────────────────────────────────────

def call_model(state: AgentState):
    """调用 LLM：自主决定调用哪些工具（或不调用）。"""
    msgs = _trim(list(state["messages"]))
    sys_msg = SystemMessage(content=SYSTEM_PROMPT.format(
        current_time=datetime.now().strftime("%Y-%m-%d %H:%M")))
    # 加载已持久化的历史摘要，帮助 LLM 记住长期上下文
    try:
        from src.tools.note_tools import get_client
        client = get_client()
        summaries = client.conn.execute(
            "SELECT summary FROM summaries ORDER BY id DESC LIMIT 3"
        ).fetchall()
        if summaries:
            summary_text = "\n".join(s[0] for s in summaries)
            msgs.insert(0, SystemMessage(content=f"[历史对话摘要]\n{summary_text}"))
    except Exception:
        pass
    response = _get_llm_with_tools().invoke([sys_msg] + msgs)
    # token 统计
    try:
        from src.core.token_tracker import get_tracker
        get_tracker().count_messages([sys_msg] + msgs, "agent")
        if response.content:
            get_tracker().count_output(response.content)
    except Exception:
        pass
    return {"messages": [response]}


# ── evaluate 节点 ────────────────────────────────────────────────

def evaluate(state: AgentState):
    """自修正：检查 Agent 回复质量，不够好则给出重试提示。"""
    retry_count = state.get("retry_count", 0)
    if retry_count >= MAX_RETRIES:
        # 已达最大重试次数，保存并结束
        _save_final_response(state)
        return {"retry_count": retry_count}

    messages = state["messages"]
    # 找最后一条 AI 回复和用户输入
    last_ai_content = None
    last_user_content = None
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
            if m.content:
                last_ai_content = m.content
        if isinstance(m, HumanMessage):
            last_user_content = m.content
            break

    if not last_ai_content or not last_user_content:
        _save_final_response(state)
        return {"retry_count": retry_count}

    # 如果工具已被调用过，跳过评估（工具执行后的第二轮自然会更准确）
    if _tools_have_been_called(messages):
        _save_final_response(state)
        return {"retry_count": retry_count}

    # LLM 评估回复质量
    eval_result = _get_eval_llm().invoke([
        SystemMessage(content=EVALUATE_PROMPT),
        HumanMessage(content=f"用户: {last_user_content}\n助手: {last_ai_content}")
    ])
    # token 统计：输入（prompt）+ 输出（eval 结果）
    try:
        from src.core.token_tracker import get_tracker
        tracker = get_tracker()
        tracker.count_messages([
            SystemMessage(content=EVALUATE_PROMPT),
            HumanMessage(content=f"用户: {last_user_content}\n助手: {last_ai_content}")
        ], "evaluate")
        if eval_result.content:
            tracker.count_output(eval_result.content)
    except Exception:
        pass

    if "RETRY" in eval_result.content:
        # 提取重试原因
        hint = eval_result.content.replace("RETRY", "").strip().lstrip(":")
        _retry_msg = SystemMessage(
            content=f"[自我修正] 你上一次回复可能不够充分，原因：{hint}。请重新考虑是否需要调用工具后再回答。"
        )
        return {
            "messages": [_retry_msg],
            "retry_count": retry_count + 1,
        }

    # 回复充分，保存到对话记录
    _save_final_response(state)
    return {"retry_count": retry_count}


def _save_final_response(state: AgentState):
    """将最终 AI 回复保存到 SQLite。"""
    client = get_client()
    for m in reversed(state["messages"]):
        if isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
            client.save_dialogue("assistant", m.content)
            return


# ── 路由函数 ─────────────────────────────────────────────────────

def should_continue(state: AgentState):
    """agent 节点后路由：有 tool_calls → tools，无 → evaluate（短消息直接跳过）。"""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    # token优化：短查询跳过evaluate（但身份问题无论长短都评估）
    last_user = _last_human_content(state["messages"])
    identity_keywords = ["我是谁", "我叫什么", "你记得我吗", "之前说过", "记住我",
                         "我的名字", "叫什么", "我是"]
    if last_user and len(last_user.strip()) < 20:
        if any(kw in last_user for kw in identity_keywords):
            return "evaluate"
        return END
    return "evaluate"


def route_after_evaluate(state: AgentState):
    """evaluate 后路由：有重试提示 → agent，否则 → 结束。"""
    messages = state["messages"]
    if messages:
        last = messages[-1]
        if isinstance(last, SystemMessage) and "[自我修正]" in last.content:
            return "agent"
    return END


# ── 构建 LangGraph ──────────────────────────────────────────────

workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(tools))
workflow.add_node("evaluate", evaluate)
workflow.set_entry_point("agent")
# 使用 dict 格式确保 should_continue 返回 END 时不会 KeyError
# LangGraph 0.2.27 中 list path_map 不会将 END 视为合法出口
workflow.add_conditional_edges("agent", should_continue, {
    "tools": "tools",
    "evaluate": "evaluate",
    END: END,
})
workflow.add_edge("tools", "agent")
workflow.add_conditional_edges("evaluate", route_after_evaluate, ["agent", END])

import threading
_app = None
_app_lock = threading.Lock()


def get_app():
    """懒加载单例：首次调用时创建 DB 连接 + 编译 workflow。隔离测试副作用。"""
    global _app
    if _app is None:
        with _app_lock:
            if _app is None:
                os.makedirs("data/sqlite", exist_ok=True)
                conn = sqlite3.connect("data/sqlite/companion.db", check_same_thread=False)
                saver = SqliteSaver(conn)
                _app = workflow.compile(checkpointer=saver)
    return _app


def __getattr__(name):
    """模块级 lazy load: import app 时不创建 DB 连接。"""
    if name == "app":
        return get_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
