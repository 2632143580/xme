"""测试 MemoryClient —— SQLite 持久化 / 笔记 / 摘要 / 全文搜索。"""
import pytest


def test_memory_client_init():
    """MemoryClient 初始化正常，:memory: 模式下三张表自动建好。"""
    from src.memory.client import MemoryClient
    client = MemoryClient()
    cur = client.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [r[0] for r in cur.fetchall()]
    assert "conversations" in tables
    assert "notes" in tables
    assert "summaries" in tables
    client.close()


def test_save_and_search_dialogue():
    """写入对话 → 关键字搜索。"""
    from src.memory.client import MemoryClient
    client = MemoryClient()
    client.save_dialogue("user", "你好小知")
    client.save_dialogue("assistant", "你好，有什么可以帮你的？")

    results = client.search_dialogue("你好")
    assert len(results) >= 2
    assert any(r["content"] == "你好小知" for r in results)
    assert any(r["content"] == "你好，有什么可以帮你的？" for r in results)
    client.close()


def test_save_and_search_note():
    """写入笔记 → 关键字搜索笔记。"""
    from src.memory.client import MemoryClient
    client = MemoryClient()
    client.save_note("会议", "明天下午3点产品评审")

    results = client.search_notes("产品评审")
    assert len(results) == 1
    assert results[0]["title"] == "会议"
    assert results[0]["content"] == "明天下午3点产品评审"
    client.close()


def test_save_and_search_summary():
    """写入摘要 → 关键字搜索摘要。"""
    from src.memory.client import MemoryClient
    client = MemoryClient()
    client.save_summary("用户提到了周末计划", "周末计划：周六爬山，周日看书")

    results = client.search_summaries("爬山")
    assert len(results) == 1
    assert "爬山" in results[0]["segment_text"] + results[0]["summary"]
    client.close()


def test_recent_dialogue():
    """保存多条对话后，recent_dialogue 返回最近 N 条。"""
    from src.memory.client import MemoryClient
    client = MemoryClient()
    for i in range(15):
        client.save_dialogue("user", f"消息{i}")

    recent = client.recent_dialogue(limit=10)
    assert len(recent) == 10
    # 最近的是消息14 → 消息5
    contents = [r["content"] for r in recent]
    assert "消息14" in contents
    assert "消息5" in contents
    client.close()


def test_full_text_search():
    """full_text_search 合并 dialogue + notes 结果。"""
    from src.memory.client import MemoryClient
    client = MemoryClient()
    # 强制降级：不让它调 Qdrant
    client.qdrant = None
    client.save_dialogue("user", "测试对话")
    client.save_note("测试", "测试笔记")

    results = client.full_text_search("测试")
    assert len(results) >= 2
    contents = [r.get("content", "") for r in results]
    assert any("对话" in c for c in contents)
    assert any("笔记" in c for c in contents)
    client.close()


def test_close_no_error():
    """close() 不掉。"""
    from src.memory.client import MemoryClient
    client = MemoryClient()
    client.close()
    # 无异常即通过


def test_maybe_summarize_auto_trigger():
    """_maybe_summarize() 每 10 条对话自动触发摘要生成。"""
    from src.memory.client import MemoryClient
    client = MemoryClient()
    # 插入 10 条对话
    for i in range(10):
        client.save_dialogue("user", f"测试消息{i}")

    # 检查 summaries 表应有 1 条自动摘要
    cur = client.conn.execute("SELECT COUNT(*) FROM summaries")
    count = cur.fetchone()[0]
    assert count == 1, f"期望 1 条摘要，实际 {count}"

    # 再插入 10 条，应有第 2 条摘要
    for i in range(10):
        client.save_dialogue("user", f"更多消息{i}")

    cur = client.conn.execute("SELECT COUNT(*) FROM summaries")
    count = cur.fetchone()[0]
    assert count == 2, f"期望 2 条摘要，实际 {count}"

    client.close()


def test_maybe_summarize_not_trigger_before_10():
    """对话不足 10 条时 _maybe_summarize() 不触发。"""
    from src.memory.client import MemoryClient
    client = MemoryClient()
    for i in range(9):
        client.save_dialogue("user", f"消息{i}")

    cur = client.conn.execute("SELECT COUNT(*) FROM summaries")
    count = cur.fetchone()[0]
    assert count == 0, f"不足 10 条不应有摘要，实际 {count}"

    client.close()
