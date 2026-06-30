"""图谱层测试 v6 -- 覆盖全部核心路径：

  TestInitSchema      : schema 初始化（约束、User 补 id）
  TestUpsertPreference: 四阶段 upsert（新建/更新/归档/不变/noop）
  TestUpsertPerson     : 人物写入 + KNOWS 关系 + is_self 分支
  TestUpsertEvent      : 事件写入 + EXPERIENCED 关系
  TestSoftDelete       : 软删除（归档非物理删除）
  TestQueryUserGraph   : 查询含 archived 过滤 + value 返回
  TestDegradation      : Neo4j 不可用时降级不抛异常
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Schema 初始化 ──────────────────────────────────────────────

class TestInitSchema:
    """测试 init_schema() 确保 User 节点有 id 属性。"""

    def test_init_schema_sets_user_id_only_when_null(self):
        """init_schema 只给缺 id 的 User 节点设置 id='user1'（不再暴力覆盖）。"""
        from src.memory.graph import init_schema
        mock_driver = MagicMock()
        mock_session = MagicMock()

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            init_schema()

        calls = [c[0][0] for c in mock_session.run.call_args_list]
        assert any("WHERE u.id IS NULL" in call for call in calls), \
            "init_schema 必须只对缺 id 的 User 节点设置 id"

    def test_init_schema_merges_user(self):
        """init_schema 应 MERGE User 节点。"""
        from src.memory.graph import init_schema
        mock_driver = MagicMock()
        mock_session = MagicMock()

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            init_schema()

        calls = [c[0][0] for c in mock_session.run.call_args_list]
        assert any("MERGE (u:User" in call for call in calls)

    def test_init_schema_creates_constraints(self):
        """init_schema 应创建唯一约束。"""
        from src.memory.graph import init_schema
        mock_driver = MagicMock()
        mock_session = MagicMock()

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            init_schema()

        calls = [c[0][0] for c in mock_session.run.call_args_list]
        assert any("CREATE CONSTRAINT" in call for call in calls)

    def test_init_schema_no_driver(self):
        """Neo4j 不可用时 init_schema 不抛异常。"""
        from src.memory.graph import init_schema
        with patch("src.memory.graph._get_driver", return_value=None):
            init_schema()


# ── upsert_preference 四阶段测试 ────────────────────────────────

class TestUpsertPreference:
    """测试 upsert_preference 的四种场景。"""

    def _make_mock_session(self):
        mock_session = MagicMock()
        return mock_session

    def test_create_new_preference(self):
        """场景1：不存在 → 创建新偏好（created）。"""
        from src.memory.graph import upsert_preference
        mock_driver = MagicMock()
        mock_session = self._make_mock_session()

        mock_result_single = MagicMock()
        mock_result_single.single.return_value = None
        mock_session.run.return_value = mock_result_single
        mock_session.execute_write.side_effect = lambda fn: fn(mock_session)

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()

            result = upsert_preference("咖啡", "不加糖")

        assert result == "created"

    def test_update_existing_preference(self):
        """场景2：存在且值不同 → 归档旧值 + 创建新值（updated）。"""
        from src.memory.graph import upsert_preference
        mock_driver = MagicMock()
        mock_session = self._make_mock_session()

        def mock_run(query, **kwargs):
            r = MagicMock()
            if "{status:'active'}" in query and "RETURN p.value" in query:
                rec = MagicMock()
                rec.__getitem__ = lambda self, key, d={"value": "加糖"}: d[key]
                r.single.return_value = rec
            else:
                r.single.return_value = None
            return r

        mock_session.run = mock_run

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            mock_session.execute_write.side_effect = \
                lambda fn: fn(mock_session)

            result = upsert_preference("咖啡", "不加糖")

        assert result == "updated"

    def test_unchanged_preference(self):
        """场景3：存在且值相同 → 不动（unchanged）。"""
        from src.memory.graph import upsert_preference
        mock_driver = MagicMock()
        mock_session = self._make_mock_session()

        def mock_run(query, **kwargs):
            r = MagicMock()
            if "RETURN p.value" in query:
                rec = MagicMock()
                rec.__getitem__ = lambda self, key, d={"value": "不加糖"}: d[key]
                r.single.return_value = rec
            else:
                r.single.return_value = None
            return r

        mock_session.run = mock_run

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            mock_session.execute_write.side_effect = \
                lambda fn: fn(mock_session)

            result = upsert_preference("咖啡", "不加糖")

        assert result == "unchanged"

    def test_soft_delete_preference(self):
        """场景4：存在但 value=None → 归档即软删除（archived）。"""
        from src.memory.graph import upsert_preference
        mock_driver = MagicMock()
        mock_session = self._make_mock_session()

        def mock_run(query, **kwargs):
            r = MagicMock()
            if "RETURN p.value" in query:
                rec = MagicMock()
                rec.__getitem__ = lambda self, key, d={"value": "加糖"}: d[key]
                r.single.return_value = rec
            else:
                r.single.return_value = None
            return r

        mock_session.run = mock_run

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            mock_session.execute_write.side_effect = \
                lambda fn: fn(mock_session)

            result = upsert_preference("咖啡", None)

        assert result == "archived"

    def test_noop_when_not_exist_and_no_value(self):
        """场景5：不存在且 value=None → noop。"""
        from src.memory.graph import upsert_preference
        mock_driver = MagicMock()
        mock_session = self._make_mock_session()

        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            mock_session.execute_write.side_effect = \
                lambda fn: fn(mock_session)

            result = upsert_preference("未知偏好", None)

        assert result == "noop"

    def test_neo4j_down_graceful(self):
        """Neo4j 不可用时返回 noop，不抛异常。"""
        from src.memory.graph import upsert_preference
        with patch("src.memory.graph._get_driver", return_value=None):
            result = upsert_preference("test", "value")
            assert result == "noop"


# ── upsert_person 测试 ─────────────────────────────────────────

class TestUpsertPerson:
    """测试人物写入 + KNOWS 关系 + is_self 分支。"""

    def test_is_self_creates_knows_relation(self):
        """is_self=True 时必须建立 User-KNOWS→Person 关系（v6 修复）。"""
        from src.memory.graph import upsert_person
        mock_driver = MagicMock()
        mock_session = MagicMock()

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            mock_session.execute_write.side_effect = \
                lambda fn: fn(mock_session)

            upsert_person("小明", props={"is_self": True})

        calls = [c[0][0] for c in mock_session.run.call_args_list]
        assert any("KNOWS" in call for call in calls), \
            "is_self=True 时必须创建 KNOWS 关系"

    def test_regular_person(self):
        """普通人物写入应建 Person 节点和 KNOWS 关系。"""
        from src.memory.graph import upsert_person
        mock_driver = MagicMock()
        mock_session = MagicMock()

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            mock_session.execute_write.side_effect = \
                lambda fn: fn(mock_session)

            upsert_person("老王")

        calls = [c[0][0] for c in mock_session.run.call_args_list]
        assert any("MERGE (p:Person" in call for call in calls)
        assert any("KNOWS" in call for call in calls)


# ── upsert_event 测试 ──────────────────────────────────────────

class TestUpsertEvent:
    """测试事件写入。"""

    def test_upsert_event_with_time(self):
        """带时间的事件写入。"""
        from src.memory.graph import upsert_event
        mock_driver = MagicMock()
        mock_session = MagicMock()

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            mock_session.execute_write.side_effect = \
                lambda fn: fn(mock_session)

            upsert_event("期末考试", time="下周三")

        calls = [c[0][0] for c in mock_session.run.call_args_list]
        assert any("EXPERIENCED" in call for call in calls)


# ── 软删除测试 ────────────────────────────────────────────────

class TestSoftDelete:
    """测试软删除（归档非物理删除）。"""

    def test_soft_delete_person(self):
        """软删除人物应 SET status='archived' 而非 DETACH DELETE。"""
        from src.memory.graph import soft_delete_entity
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key, d={"cnt": 1}: d[key]
        mock_result.single.return_value = mock_row
        mock_session.run.return_value = mock_result

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            mock_session.execute_write.side_effect = \
                lambda fn: fn(mock_session)

            ok = soft_delete_entity("老王", "person")

        assert ok is True
        calls = [c[0][0] for c in mock_session.run.call_args_list]
        assert any("archived" in call for call in calls)
        assert not any("DETACH DELETE" in call or "DELETE" in call
                       for call in calls)

    def test_soft_delete_nonexistent(self):
        """删除不存在的实体返回 False。"""
        from src.memory.graph import soft_delete_entity
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key, d={"cnt": 0}: d[key]
        mock_result.single.return_value = mock_row
        mock_session.run.return_value = mock_result

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            mock_session.execute_write.side_effect = \
                lambda fn: fn(mock_session)

            ok = soft_delete_entity("不存在的人", "person")

        assert ok is False

    def test_delete_entity_deprecated_calls_soft_delete(self):
        """delete_entity 内部应调用 soft_delete_entity。"""
        from src.memory.graph import delete_entity
        with patch("src.memory.graph.soft_delete_entity",
                   return_value=True) as mock_soft:
            result = delete_entity("test", "person")
            mock_soft.assert_called_once_with("test", "person")
            assert result is True


# ── 查询测试（含 archived 过滤）────────────────────────────────

class TestQueryUserGraph:
    """测试 query_user_graph 含 active 过滤和 value 返回。"""

    def test_query_filters_active(self):
        """查询必须过滤 archived 关系。"""
        from src.memory.graph import query_user_graph
        mock_driver = MagicMock()
        mock_session = MagicMock()

        def mock_run(query, **kwargs):
            r = MagicMock()
            if "HAS_PREFERENCE" in query:
                assert "active" in query.lower(), \
                    "查询偏好关系必须过滤 active 状态"
                r.__iter__ = lambda _: iter([])
            elif "EXPERIENCED" in query:
                assert "active" in query.lower(), \
                    "查询事件关系必须过滤 active 状态"
                r.__iter__ = lambda _: iter([])
            elif "KNOWS" in query:
                assert "active" in query.lower(), \
                    "查询人物关系必须过滤 active 状态"
                r.__iter__ = lambda _: iter([])
            elif "RETURN u.name" in query:
                r.__iter__ = lambda _: iter([{"name": "豆包"}])
            else:
                r.__iter__ = lambda _: iter([])
            return r

        mock_session.run = mock_run

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            result = query_user_graph()

        assert result["user_name"] == "豆包"
        assert "preferences" in result
        assert "events" in result
        assert "people" in result

    def test_query_returns_preference_values(self):
        """查询应返回带 value 的偏好列表。"""
        from src.memory.graph import query_user_graph
        mock_driver = MagicMock()
        mock_session = MagicMock()

        def mock_run(query, **kwargs):
            r = MagicMock()
            if "RETURN u.name" in query:
                r.__iter__ = lambda _: iter([{"name": "豆包"}])
            elif "HAS_PREFERENCE" in query:
                r.__iter__ = lambda _: iter([
                    {"name": "咖啡", "value": "不加糖"},
                    {"name": "运动", "value": "跑步"},
                ])
            elif "EXPERIENCED" in query:
                r.__iter__ = lambda _: iter([])
            elif "KNOWS" in query:
                r.__iter__ = lambda _: iter([])
            return r

        mock_session.run = mock_run

        with patch("src.memory.graph._get_driver", return_value=mock_driver):
            mock_driver.session.return_value.__enter__ = lambda _: mock_session
            mock_driver.session.return_value.__exit__ = MagicMock()
            result = query_user_graph()

        pref_names = [p["name"] for p in result["preferences"]]
        pref_values = [p["value"] for p in result["preferences"]]
        assert "咖啡" in pref_names
        assert "不加糖" in pref_values
        assert "运动" in pref_names
        assert "跑步" in pref_values

    def test_query_no_driver(self):
        """Neo4j 不可用时返回空字典。"""
        from src.memory.graph import query_user_graph
        with patch("src.memory.graph._get_driver", return_value=None):
            result = query_user_graph()
            assert result == {}


# ── 降级测试 ──────────────────────────────────────────────────

class TestDegradation:
    """Neo4j 不可用时所有操作降级不抛异常。"""

    @pytest.mark.parametrize("func,args", [
        ("upsert_person", ("老王",)),
        ("upsert_preference", ("咖啡", "不加糖")),
        ("upsert_event", ("考试",)),
        ("add_person_relation", ("老王", "同事", "小李")),
        ("soft_delete_entity", ("老王", "person")),
        ("query_user_graph", ()),
    ])
    def test_no_crash_without_neo4j(self, func, args):
        """Neo4j 不可用时所有函数不抛异常。"""
        from src.memory.graph import (
            upsert_person, upsert_preference, upsert_event,
            add_person_relation, soft_delete_entity, query_user_graph,
        )
        func_map = {
            "upsert_person": upsert_person,
            "upsert_preference": upsert_preference,
            "upsert_event": upsert_event,
            "add_person_relation": add_person_relation,
            "soft_delete_entity": soft_delete_entity,
            "query_user_graph": query_user_graph,
        }
        with patch("src.memory.graph._get_driver", return_value=None):
            result = func_map[func](*args)
            if func == "query_user_graph":
                assert result == {}
            elif func == "upsert_preference":
                assert result == "noop"
            elif func == "soft_delete_entity":
                assert result is False
            else:
                assert result is None
