"""测试 agent 核心 -- Agentic RAG: 滑动窗口 / 自主决策 / evaluate 自修正 / 路由。"""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage


# ── _trim ---------------------------------------------------------

def test_trim_small_window():
    """消息数 <= MAX_WINDOW 时原样返回。"""
    from src.core.agent import _trim
    msgs = [HumanMessage(content=f"msg{i}") for i in range(5)]
    result = _trim(msgs)
    assert len(result) == 5
    assert result == msgs


def test_trim_large_window():
    """消息数 > MAX_WINDOW 时截断到窗口大小。"""
    from src.core.agent import _trim, MAX_WINDOW
    msgs = [HumanMessage(content=f"msg{i}") for i in range(MAX_WINDOW + 10)]
    result = _trim(msgs)
    assert len(result) == MAX_WINDOW


def test_trim_preserves_tool_message():
    """截断时如果开头是 ToolMessage，往前补一条。"""
    from src.core.agent import _trim, MAX_WINDOW
    msgs = [HumanMessage(content=f"msg{i}") for i in range(MAX_WINDOW + 1)]
    msgs.append(ToolMessage(content="tool result", tool_call_id="call_1"))
    result = _trim(msgs)
    assert len(result) == MAX_WINDOW
    assert isinstance(result[-1], ToolMessage)


# ── _last_human_content -------------------------------------------

def test_last_human_content():
    from src.core.agent import _last_human_content
    msgs = [
        HumanMessage(content="第一个问题"),
        AIMessage(content="第一个回答"),
        HumanMessage(content="第二个问题"),
    ]
    assert _last_human_content(msgs) == "第二个问题"


def test_last_human_content_no_human():
    from src.core.agent import _last_human_content
    msgs = [AIMessage(content="只有 AI")]
    assert _last_human_content(msgs) is None


# ── _tools_have_been_called ---------------------------------------

_TC_ARGS = {"id": "call_1", "name": "create_note", "args": {}}


def test_tools_have_been_called_true():
    from src.core.agent import _tools_have_been_called
    msgs = [
        HumanMessage(content="hi"),
        AIMessage(content="ok", tool_calls=[_TC_ARGS]),
        ToolMessage(content="done", tool_call_id="call_1"),
    ]
    assert _tools_have_been_called(msgs) is True


def test_tools_have_been_called_false():
    from src.core.agent import _tools_have_been_called
    msgs = [HumanMessage(content="hi"), AIMessage(content="ok")]
    assert _tools_have_been_called(msgs) is False


# ── should_continue -----------------------------------------------

def test_should_continue_tools():
    """agent 输出有 tool_calls → 路由到 tools。"""
    from src.core.agent import should_continue
    msg = AIMessage(content="ok", tool_calls=[_TC_ARGS])
    state = {"messages": [msg], "retry_count": 0}
    assert should_continue(state) == "tools"


def test_should_continue_evaluate():
    """agent 输出无 tool_calls → 路由到 evaluate（不再是 END）。"""
    from src.core.agent import should_continue
    msg = AIMessage(content="你好！")
    state = {"messages": [msg], "retry_count": 0}
    assert should_continue(state) == "evaluate"


# ── route_after_evaluate -------------------------------------------

def test_route_after_evaluate_retry():
    """evaluate 输出含 [自我修正] → 路由回 agent。"""
    from src.core.agent import route_after_evaluate
    hint = SystemMessage(content="[自我修正] 未检索记忆，请重新考虑。")
    state = {"messages": [hint], "retry_count": 1}
    assert route_after_evaluate(state) == "agent"


def test_route_after_evaluate_sufficient():
    """evaluate 输出不含 [自我修正] → 路由到 END。"""
    from src.core.agent import route_after_evaluate
    from langgraph.graph import END
    state = {"messages": [AIMessage(content="好的")], "retry_count": 0}
    assert route_after_evaluate(state) == END


def test_route_after_evaluate_empty():
    """无消息 → END。"""
    from src.core.agent import route_after_evaluate
    from langgraph.graph import END
    state = {"messages": [], "retry_count": 0}
    assert route_after_evaluate(state) == END


# ── evaluate 自修正 -----------------------------------------------

def _mock_eval_llm(response_text):
    """构造 mock eval_llm。"""
    mock = MagicMock()
    mock.invoke.return_value = AIMessage(content=response_text)
    return lambda: mock


def test_evaluate_sufficient():
    """evaluate 判定 SUFFICIENT → 不生成重试提示。"""
    from src.core.agent import evaluate

    mock_client = MagicMock()
    with patch("src.core.agent.get_client", return_value=mock_client), \
         patch("src.core.agent._get_eval_llm", _mock_eval_llm("SUFFICIENT")):
        state = {
            "messages": [
                HumanMessage(content="今天天气不错"),
                AIMessage(content="是啊阳光很好"),
            ],
            "retry_count": 0,
        }
        result = evaluate(state)
        assert result["retry_count"] == 0
        # 不应有 [自我修正] 消息
        for m in result.get("messages", []):
            assert "[自我修正]" not in getattr(m, "content", "")
        # 最终回复应被保存
        mock_client.save_dialogue.assert_called()


def test_evaluate_retry_needed():
    """evaluate 判定 RETRY → 生成 [自我修正] 提示，retry_count +1。"""
    from src.core.agent import evaluate

    mock_client = MagicMock()
    with patch("src.core.agent.get_client", return_value=mock_client), \
         patch("src.core.agent._get_eval_llm", _mock_eval_llm("RETRY:未检索记忆")):
        state = {
            "messages": [
                HumanMessage(content="我是谁"),
                AIMessage(content="你是我超贴心的好朋友呀"),
            ],
            "retry_count": 0,
        }
        result = evaluate(state)
        assert result["retry_count"] == 1
        # 应有 [自我修正] 消息
        hint_msgs = [m for m in result.get("messages", [])
                     if isinstance(m, SystemMessage) and "[自我修正]" in m.content]
        assert len(hint_msgs) == 1
        # 最终回复不应被保存（等待重试）
        mock_client.save_dialogue.assert_not_called()


def test_evaluate_max_retries_reached():
    """已达 MAX_RETRIES → 不再重试，保存回复。"""
    from src.core.agent import evaluate, MAX_RETRIES

    mock_client = MagicMock()
    with patch("src.core.agent.get_client", return_value=mock_client), \
         patch("src.core.agent._get_eval_llm", _mock_eval_llm("RETRY:未检索记忆")):
        state = {
            "messages": [
                HumanMessage(content="我是谁"),
                AIMessage(content="我还是不知道你的名字"),
            ],
            "retry_count": MAX_RETRIES,
        }
        result = evaluate(state)
        assert result["retry_count"] == MAX_RETRIES
        # 不应有 [自我修正] 消息
        for m in result.get("messages", []):
            assert "[自我修正]" not in getattr(m, "content", "")
        # 最终回复应被保存
        mock_client.save_dialogue.assert_called()


def test_evaluate_skip_if_tools_called():
    """如果工具已被调用过，跳过评估直接保存。"""
    from src.core.agent import evaluate

    mock_client = MagicMock()
    # 不需要 mock eval_llm（因为不会被调用）
    with patch("src.core.agent.get_client", return_value=mock_client):
        state = {
            "messages": [
                HumanMessage(content="我之前说过什么"),
                AIMessage(content="", tool_calls=[_TC_ARGS]),
                ToolMessage(content="找到了笔记", tool_call_id="call_1"),
                AIMessage(content="你之前说过..."),
            ],
            "retry_count": 0,
        }
        result = evaluate(state)
        assert result["retry_count"] == 0
        # 不应有 [自我修正] 消息
        for m in result.get("messages", []):
            assert "[自我修正]" not in getattr(m, "content", "")
        mock_client.save_dialogue.assert_called()


# ── call_model ----------------------------------------------------

def test_call_model_with_mock():
    """call_model 正常返回 AIMessage。"""
    from src.core.agent import call_model

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content="你好！")

    with patch("src.core.agent._get_llm_with_tools", return_value=mock_llm):
        state = call_model({"messages": [HumanMessage(content="你好")]})
        assert state["messages"][0].content == "你好！"


# ── 工具列表 -------------------------------------------------------

def test_tools_list():
    """tools 列表包含所有注册工具。"""
    from src.core.agent import tools
    tool_names = [t.name for t in tools]
    assert "create_note" in tool_names
    assert "retrieve_memory" in tool_names
    assert "write_to_graph" in tool_names
    assert "delete_note" in tool_names
    assert "update_note" in tool_names
    assert "list_notes" in tool_names
    assert "query_graph" in tool_names
    assert "delete_from_graph" in tool_names
    assert len(tools) == 8


# ── 确保无硬编码关键词 -------------------------------------------

def test_no_keyword_lists():
    """确认 agent.py 不存在硬编码关键词列表。"""
    import src.core.agent as agent_module
    source = open(agent_module.__file__, encoding="utf-8").read()
    # 不应存在这些关键词列表
    assert "_U_KEYWORDS" not in source
    assert "_A_KEYWORDS" not in source
    assert "_NAME_KEYWORDS" not in source
    assert "_need_force_note" not in source
    assert "_extract_user_name" not in source


# ── evaluate prompt 无触发规则 -----------------------------------

def test_prompt_is_autonomous():
    """确认 SYSTEM_PROMPT 不含触发规则关键词，只有自主决策原则。"""
    from src.memory.prompts import SYSTEM_PROMPT
    # 不应有具体的触发词指令
    assert "记一下" not in SYSTEM_PROMPT or "自主决策" in SYSTEM_PROMPT
    assert "我是谁" not in SYSTEM_PROMPT or "自主决策" in SYSTEM_PROMPT
    # 应有自主决策原则
    assert "自主决策" in SYSTEM_PROMPT
