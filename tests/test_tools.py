"""测试 note_tools 模块。"""
import pytest
from unittest.mock import MagicMock, patch


def test_create_note_tool():
    """测试 create_note 工具函数。"""
    with patch("src.tools.note_tools.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.save_note.return_value = 1
        mock_get_client.return_value = mock_client

        from src.tools.note_tools import create_note
        result = create_note.invoke({"content": "测试笔记内容"})

        assert "已记录" in result
        assert "ID:1" in result
        mock_client.save_note.assert_called_once()


def test_retrieve_memory_tool():
    """测试 retrieve_memory 工具函数（第二阶段：full_text_search）。"""
    with patch("src.tools.note_tools.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.full_text_search.return_value = [
            {"title": "测试", "content": "内容"}
        ]
        mock_get_client.return_value = mock_client

        from src.tools.note_tools import retrieve_memory
        result = retrieve_memory.invoke({"query": "测试"})

        assert "笔记" in result
        assert "内容" in result
        mock_client.full_text_search.assert_called_once_with("测试", limit=5)


def test_get_client_caching():
    """测试 get_client 缓存。"""
    from src.tools.note_tools import get_client
    # 清除缓存
    get_client.cache_clear()
    client1 = get_client()
    client2 = get_client()
    assert client1 is client2  # 应该返回同一个实例


def test_write_to_graph_preference():
    """测试 write_to_graph 工具 -- preference 类型。"""
    with patch("src.tools.graph_tools.graph_module.upsert_preference",
               return_value="created") as mock:
        from src.tools.graph_tools import write_to_graph
        result = write_to_graph.invoke({
            "entity_type": "preference",
            "entity_name": "咖啡",
        })
        assert "喜欢" in result
        assert "咖啡" in result
        mock.assert_called_once_with("咖啡", None, uid="user1")


def test_write_to_graph_person():
    """测试 write_to_graph 工具 -- person 类型。"""
    with patch("src.tools.graph_tools.graph_module.upsert_person") as mock_person:
        from src.tools.graph_tools import write_to_graph
        result = write_to_graph.invoke({
            "entity_type": "person",
            "entity_name": "老王",
        })
        assert "认识" in result
        assert "老王" in result
        mock_person.assert_called_once_with("老王", uid="user1")


def test_write_to_graph_person_with_relation():
    """测试 write_to_graph 工具 -- person + relation。"""
    with patch("src.tools.graph_tools.graph_module.upsert_person") as mock_person, \
         patch("src.tools.graph_tools.graph_module.add_person_relation") as mock_rel:
        from src.tools.graph_tools import write_to_graph
        result = write_to_graph.invoke({
            "entity_type": "person",
            "entity_name": "老王",
            "relation_type": "同事",
            "related_to": "小李",
        })
        assert "同事" in result
        mock_person.assert_called_once_with("老王", uid="user1")
        mock_rel.assert_called_once_with("老王", "同事", "小李", uid="user1")


def test_write_to_graph_event():
    """测试 write_to_graph 工具 -- event 类型。"""
    with patch("src.tools.graph_tools.graph_module.upsert_event") as mock:
        from src.tools.graph_tools import write_to_graph
        result = write_to_graph.invoke({
            "entity_type": "event",
            "entity_name": "期末考试",
            "time": "下周三",
        })
        assert "事件" in result
        assert "期末考试" in result
        mock.assert_called_once_with("期末考试", time="下周三", uid="user1")


def test_write_to_graph_unknown_type():
    """测试 write_to_graph 工具 -- 不支持的类型。"""
    from src.tools.graph_tools import write_to_graph
    result = write_to_graph.invoke({
        "entity_type": "unknown",
        "entity_name": "test",
    })
    assert "不支持" in result
