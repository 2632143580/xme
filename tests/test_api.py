"""API 层测试 -- FastAPI endpoint 验证。

所有测试使用 TestClient（不需要真实启动 uvicorn），mock 外部依赖。
"""
import os
import sys
import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

# 确保 demo 根目录在 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestConfigAPI:
    """测试 GET/PUT /api/config。"""

    def test_get_config_returns_all_env_vars(self, tmp_path):
        """GET /api/config 返回所有 .env 参数。"""
        from fastapi.testclient import TestClient
        from src.api.server import api_app

        env_content = "LLM_PROVIDER=volcengine\nVOLCENGINE_API_KEY=7ab7test1234\nENABLE_SCHEDULER=false\n"
        env_path = tmp_path / ".env"
        env_path.write_text(env_content, encoding="utf-8")

        with patch("src.config.ENV_FILE", str(env_path)):
            from src.config import get_settings
            get_settings.cache_clear()

            with TestClient(api_app) as client:
                resp = client.get("/api/config")
                assert resp.status_code == 200
                data = resp.json()
                assert "LLM_PROVIDER" in data
                assert "VOLCENGINE_API_KEY" in data
                # API Key 应脱敏
                key_display = data["VOLCENGINE_API_KEY"]["value"]
                assert "****" in key_display or key_display == ""

    def test_put_config_writes_env(self, tmp_path):
        """PUT /api/config 修改 .env 并返回 need_restart 标记。"""
        env_content = "LLM_PROVIDER=volcengine\nIDLE_THRESHOLD_MINUTES=30\nENABLE_SCHEDULER=false\n"
        env_path = tmp_path / ".env"
        env_path.write_text(env_content, encoding="utf-8")

        from fastapi.testclient import TestClient
        from src.api.server import api_app

        with patch("src.config.ENV_FILE", str(env_path)):
            from src.config import get_settings
            get_settings.cache_clear()

            with TestClient(api_app) as client:
                resp = client.put("/api/config", json={
                    "IDLE_THRESHOLD_MINUTES": "45",
                })
                assert resp.status_code == 200
                data = resp.json()
                assert "IDLE_THRESHOLD_MINUTES" in data["updated"]
                assert data["need_restart"] is False  # 热更新参数

                # 验证 .env 已改写
                new_env = env_path.read_text(encoding="utf-8")
                assert "IDLE_THRESHOLD_MINUTES=45" in new_env

    def test_put_config_need_restart(self, tmp_path):
        """PUT /api/config 修改 SQLITE_PATH 标记 need_restart=True。"""
        env_content = "SQLITE_PATH=data/sqlite/test.db\n"
        env_path = tmp_path / ".env"
        env_path.write_text(env_content, encoding="utf-8")

        from fastapi.testclient import TestClient
        from src.api.server import api_app

        with patch("src.config.ENV_FILE", str(env_path)):
            from src.config import get_settings
            get_settings.cache_clear()

            with TestClient(api_app) as client:
                resp = client.put("/api/config", json={
                    "SQLITE_PATH": "data/sqlite/new.db",
                })
                assert resp.status_code == 200
                data = resp.json()
                assert data["need_restart"] is True


class TestStatusAPI:
    """测试 GET /api/status。"""

    def test_status_returns_all_sections(self):
        """GET /api/status 返回 connections/statistics/scheduler/runtime/graph/pending_reminders。"""
        from fastapi.testclient import TestClient
        from src.api.server import api_app

        mock_client = MagicMock()
        mock_client.qdrant = None
        mock_client.conn = MagicMock()
        mock_client.conn.execute.return_value.fetchone.side_effect = [10, 5, 2]

        with patch("src.tools.note_tools.get_client", return_value=mock_client), \
             patch("src.core.scheduler.get_scheduler_status", return_value={
                 "running": False, "workers": 0, "timezone": "Asia/Shanghai", "jobs": []
             }), \
             patch("src.core.scheduler.get_idle_minutes", return_value=0.0), \
             patch("src.core.scheduler.get_pending_reminders", return_value=[]), \
             patch("src.api.server.query_user_graph", return_value={}):
            with TestClient(api_app) as client:
                resp = client.get("/api/status")
                assert resp.status_code == 200
                data = resp.json()
                assert "connections" in data
                assert "statistics" in data
                assert "scheduler" in data
                assert "runtime" in data
                assert "graph" in data
                assert "pending_reminders" in data


class TestDialogueAPI:
    """测试 GET /api/dialogues。"""

    def test_get_dialogues_returns_list(self):
        """GET /api/dialogues 返回对话列表。"""
        from fastapi.testclient import TestClient
        from src.api.server import api_app

        mock_client = MagicMock()
        mock_client.recent_dialogue.return_value = [
            {"role": "user", "content": "你好", "created_at": "2026-06-27 10:00:00"},
        ]

        with patch("src.api.server.get_client", return_value=mock_client):
            with TestClient(api_app) as client:
                resp = client.get("/api/dialogues?limit=10")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data) >= 1
                assert data[0]["role"] in ("user", "assistant")


class TestReminderAPI:
    """测试 POST/DELETE /api/reminders。"""

    def test_create_reminder_valid(self):
        """POST /api/reminders 创建提醒。"""
        from fastapi.testclient import TestClient
        from src.api.server import api_app

        with patch("src.api.server.register_reminder") as mock_reg:
            with TestClient(api_app) as client:
                resp = client.post("/api/reminders", json={
                    "content": "开会",
                    "time": "2026-12-31T14:30",
                })
                assert resp.status_code == 200
                mock_reg.assert_called_once()

    def test_create_reminder_past_time_fails(self):
        """POST /api/reminders 过去时间返回 400。"""
        from fastapi.testclient import TestClient
        from src.api.server import api_app

        with TestClient(api_app) as client:
            resp = client.post("/api/reminders", json={
                "content": "开会",
                "time": "2020-01-01T10:00",
            })
            assert resp.status_code == 400

    def test_delete_reminder_not_found(self):
        """DELETE /api/reminders/:id 不存在的提醒返回 404。"""
        from fastapi.testclient import TestClient
        from src.api.server import api_app

        with patch("src.api.server.remove_reminder", return_value=False):
            with TestClient(api_app) as client:
                resp = client.delete("/api/reminders/reminder_nonexistent")
                assert resp.status_code == 404


class TestLogAPI:
    """测试 GET /api/logs。"""

    def test_get_logs_returns_buffer(self):
        """GET /api/logs 返回日志缓冲区内容。"""
        from fastapi.testclient import TestClient
        from src.api.server import api_app
        from src.core.scheduler import add_log, _log_buffer

        # 清空缓冲区再写入测试日志
        _log_buffer.clear()
        add_log("info", "测试日志_API")

        with TestClient(api_app) as client:
            resp = client.get("/api/logs?limit=10")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) >= 1
            # 找到测试日志（startup 也会写日志）
            found = any(d["message"] == "测试日志_API" for d in data)
            assert found


class TestGraphAPI:
    """测试 GET /api/graph。"""

    def test_get_graph_returns_data(self):
        """GET /api/graph 返回图谱摘要。"""
        from fastapi.testclient import TestClient
        from src.api.server import api_app

        with patch("src.api.server.query_user_graph", return_value={
            "preferences": ["阅读"], "events": [{"title": "生日"}], "people": ["张三"]
        }):
            with TestClient(api_app) as client:
                resp = client.get("/api/graph")
                assert resp.status_code == 200
                data = resp.json()
                assert "preferences" in data
                assert len(data["preferences"]) >= 1


class TestConfigWriteEnv:
    """测试 config.py write_env 函数。"""

    def test_write_env_preserves_comments(self, tmp_path):
        """write_env 保留注释行。"""
        from src.config import write_env

        env_content = "# 这是注释\nLLM_PROVIDER=volcengine\nIDLE_THRESHOLD_MINUTES=30\n"
        env_path = tmp_path / ".env"
        env_path.write_text(env_content, encoding="utf-8")

        with patch("src.config.ENV_FILE", str(env_path)):
            updated = write_env({"IDLE_THRESHOLD_MINUTES": "60"})
            assert "IDLE_THRESHOLD_MINUTES" in updated

            result = env_path.read_text(encoding="utf-8")
            assert "# 这是注释" in result
            assert "IDLE_THRESHOLD_MINUTES=60" in result

    def test_write_env_appends_new_var(self, tmp_path):
        """write_env 追加不存在的新变量。"""
        from src.config import write_env

        env_content = "LLM_PROVIDER=volcengine\n"
        env_path = tmp_path / ".env"
        env_path.write_text(env_content, encoding="utf-8")

        with patch("src.config.ENV_FILE", str(env_path)):
            updated = write_env({"NEW_VAR": "new_value"})
            assert "NEW_VAR" in updated

            result = env_path.read_text(encoding="utf-8")
            assert "NEW_VAR=new_value" in result

    def test_mask_secret(self):
        """mask_secret 脱敏只露前4位。"""
        from src.config import mask_secret

        assert mask_secret("7ab7e77d-5be7") == "7ab7****"
        assert mask_secret("abc") == "****"
        assert mask_secret("") == ""


class TestSchedulerHotUpdate:
    """测试调度器热更新接口。"""

    def test_hot_update_idle_threshold(self):
        """hot_update_idle_threshold 更新全局变量。"""
        from src.core.scheduler import hot_update_idle_threshold, IDLE_THRESHOLD_MINUTES

        result = hot_update_idle_threshold(60)
        assert result is True
        # 验证全局变量已更新
        from src.core.scheduler import IDLE_THRESHOLD_MINUTES
        assert IDLE_THRESHOLD_MINUTES == 60

    def test_hot_update_greeting_no_scheduler(self):
        """调度器未运行时 hot_update_greeting 返回 False。"""
        from src.core.scheduler import hot_update_greeting
        import src.core.scheduler as sched

        original_scheduler = sched._scheduler
        sched._scheduler = None

        result = hot_update_greeting(8, 30)
        assert result is False

        sched._scheduler = original_scheduler

    def test_add_log_and_get_logs(self):
        """add_log 写入缓冲区，get_logs 返回内容。"""
        from src.core.scheduler import add_log, get_logs, _log_buffer

        _log_buffer.clear()

        add_log("info", "测试日志1")
        add_log("warn", "警告日志2")

        logs = get_logs(limit=10)
        assert len(logs) == 2
        # 最新在前（BugFix: logs now newest-first）
        assert logs[0]["level"] == "warn"
        assert logs[1]["level"] == "info"

    def test_get_scheduler_status(self):
        """get_scheduler_status 返回正确结构。"""
        from src.core.scheduler import get_scheduler_status
        import src.core.scheduler as sched

        sched._scheduler = None

        status = get_scheduler_status()
        assert status["running"] is False
        assert "workers" in status
        assert "timezone" in status
        assert "jobs" in status
