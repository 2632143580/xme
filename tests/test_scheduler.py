"""调度器测试 -- 时间意图提取、空闲检测、主动对话判断、持久态调度器初始化。"""
import sys
import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, ANY

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.scheduler import (
    extract_reminder_time, should_proactively_engage,
    record_user_activity, get_idle_minutes, get_pending_reminders,
    start_scheduler, stop_scheduler, register_reminder,
    set_reminder_queue, _default_reminder_callback,
    IDLE_THRESHOLD_MINUTES, _ensure_data_dir,
    add_log, get_logs, _log_buffer,
)


# ── 时间意图提取 ──────────────────────────────────────────

class TestExtractReminderTime:
    """测试 extract_reminder_time 从文本提取时间意图。"""

    def test_relative_day_afternoon(self):
        now = datetime(2026, 6, 27, 10, 0)
        result = extract_reminder_time("明天下午3点开会", now)
        assert result is not None
        assert result.hour == 15
        assert result.minute == 0
        assert result.day == 28

    def test_relative_day_morning(self):
        now = datetime(2026, 6, 27, 10, 0)
        result = extract_reminder_time("明天上午9点出发", now)
        assert result is not None
        assert result.hour == 9
        assert result.minute == 0

    def test_two_days_later(self):
        now = datetime(2026, 6, 27, 10, 0)
        result = extract_reminder_time("后天下午2点", now)
        assert result is not None
        assert result.day == 29
        assert result.hour == 14

    def test_today_time_with_period(self):
        now = datetime(2026, 6, 27, 10, 0)
        result = extract_reminder_time("下午3点半回家", now)
        assert result is not None
        assert result.hour == 15
        assert result.minute == 30

    def test_next_weekday(self):
        now = datetime(2026, 6, 27, 10, 0)  # Saturday
        result = extract_reminder_time("下周一下午2点", now)
        assert result is not None
        assert result.isoweekday() == 1  # Monday
        assert result.hour == 14

    def test_no_time_intent(self):
        result = extract_reminder_time("随便聊聊天")
        assert result is None or (result and result > datetime.now())

    def test_past_time_returns_none(self):
        now = datetime(2026, 6, 27, 20, 0)
        result = extract_reminder_time("下午3点开会", now)
        assert result is None

    # ── 相对时长 ──

    def test_seconds_later(self):
        now = datetime(2026, 6, 27, 10, 0)
        result = extract_reminder_time("10秒后提醒我", now)
        assert result is not None
        assert result == now + timedelta(seconds=10)

    def test_minutes_later(self):
        now = datetime(2026, 6, 27, 10, 0)
        result = extract_reminder_time("5分钟后说爱我", now)
        assert result is not None
        assert result == now + timedelta(minutes=5)

    def test_hours_later(self):
        now = datetime(2026, 6, 27, 10, 0)
        result = extract_reminder_time("1小时后开会", now)
        assert result is not None
        assert result == now + timedelta(hours=1)

    def test_english_unit_s(self):
        now = datetime(2026, 6, 27, 10, 0)
        result = extract_reminder_time("10s后", now)
        assert result is not None
        assert result == now + timedelta(seconds=10)

    def test_english_unit_min(self):
        now = datetime(2026, 6, 27, 10, 0)
        result = extract_reminder_time("5min后", now)
        assert result is not None
        assert result == now + timedelta(minutes=5)

    def test_30_seconds(self):
        now = datetime(2026, 6, 27, 10, 0)
        result = extract_reminder_time("30秒后", now)
        assert result is not None
        assert result == now + timedelta(seconds=30)

    def test_relative_without_hou_suffix(self):
        """用户实际输入常不带'后'字，如 '10s说爱我' '30秒还说到'。"""
        now = datetime(2026, 6, 27, 10, 0)
        r = extract_reminder_time("10s说爱我", now)
        assert r is not None
        assert r == now + timedelta(seconds=10)

    def test_30sec_without_hou(self):
        now = datetime(2026, 6, 27, 10, 0)
        r = extract_reminder_time("30秒还买到你说了", now)
        assert r is not None
        assert r == now + timedelta(seconds=30)


# ── 主动对话判断 ──────────────────────────────────────────

class TestShouldProactivelyEngage:
    """测试 should_proactively_engage 判断逻辑。"""

    def setup_method(self):
        """每个测试前恢复 IDLE_THRESHOLD_MINUTES 默认值。"""
        import src.core.scheduler as sched
        sched.IDLE_THRESHOLD_MINUTES = 30

    def test_idle_morning_greeting(self):
        context = {"current_time": "09:30", "idle_minutes": 35}
        engage, content = should_proactively_engage(context)
        assert engage is True
        assert "早上" in content

    def test_idle_afternoon_greeting(self):
        context = {"current_time": "15:00", "idle_minutes": 40}
        engage, content = should_proactively_engage(context)
        assert engage is True
        assert "下午" in content

    def test_idle_evening_greeting(self):
        context = {"current_time": "21:00", "idle_minutes": 45}
        engage, content = should_proactively_engage(context)
        assert engage is True
        assert "晚上" in content

    def test_no_engage_when_active(self):
        context = {"current_time": "14:00", "idle_minutes": 5}
        engage, content = should_proactively_engage(context)
        assert engage is False
        assert content == ""

    def test_pending_reminder_triggers(self):
        context = {
            "current_time": "14:55",
            "idle_minutes": 5,
            "pending_reminders": [
                {"content": "3点开会", "due_time": "14:58", "due_soon": True}
            ],
        }
        engage, content = should_proactively_engage(context)
        assert engage is True
        assert "开会" in content

    def test_reminder_priority_over_idle(self):
        context = {
            "current_time": "09:00",
            "idle_minutes": 60,
            "pending_reminders": [
                {"content": "9点开会", "due_time": "09:00", "due_soon": True}
            ],
        }
        engage, content = should_proactively_engage(context)
        assert engage is True
        assert "提醒" in content

    def test_night_greeting(self):
        context = {"current_time": "02:00", "idle_minutes": 60}
        engage, content = should_proactively_engage(context)
        assert engage is True
        assert "休息" in content


# ── 空闲追踪 ──────────────────────────────────────────────

class TestIdleTracking:
    """测试空闲时间记录和计算。"""

    def test_record_and_get_idle(self):
        record_user_activity()
        idle = get_idle_minutes()
        assert idle >= 0
        assert idle < 1

    def test_idle_threshold_default(self):
        assert IDLE_THRESHOLD_MINUTES == 30


# ── 数据目录创建 ──────────────────────────────────────────

class TestEnsureDataDir:
    """测试 _ensure_data_dir 创建目录。"""

    def test_creates_missing_dir(self, tmp_path):
        db_path = tmp_path / "sub" / "deep" / "jobs.sqlite"
        _ensure_data_dir(str(db_path))
        assert os.path.exists(str(db_path.parent))

    def test_no_error_when_exists(self, tmp_path):
        os.makedirs(str(tmp_path / "db"), exist_ok=True)
        # 不应抛异常
        _ensure_data_dir(str(tmp_path / "db" / "jobs.sqlite"))


# ── 持久态调度器初始化 ───────────────────────────────────

# 调度器内部 import 的目标路径（函数内 import，需 patch apscheduler 模块）
_APS_BG = "apscheduler.schedulers.background.BackgroundScheduler"
_APS_STORE = "apscheduler.jobstores.sqlalchemy.SQLAlchemyJobStore"
_APS_TP = "apscheduler.executors.pool.ThreadPoolExecutor"


class TestStartScheduler:
    """测试 start_scheduler 初始化持久态调度器。"""

    def test_disabled_when_flag_false(self, monkeypatch):
        """ENABLE_SCHEDULER=false 时用 add_log 记录而非 print。"""
        monkeypatch.setattr(
            "src.core.scheduler.get_settings",
            lambda: {"enable_scheduler": False},
        )
        import src.core.scheduler as sched
        sched._scheduler = None
        from src.core.scheduler import _log_buffer, get_logs
        _log_buffer.clear()
        start_scheduler()
        logs = get_logs(limit=5)
        assert any("关闭" in l["message"] or "false" in l["message"] for l in logs)

    @patch(_APS_BG)
    @patch(_APS_STORE)
    @patch(_APS_TP)
    def test_init_with_persistent_store(self, mock_tp, mock_store, mock_bg,
                                         monkeypatch, tmp_path):
        """验证持久态调度器使用 SQLAlchemyJobStore + ThreadPoolExecutor。"""
        db_path = tmp_path / "jobs.sqlite"
        monkeypatch.setattr(
            "src.core.scheduler.get_settings",
            lambda: {
                "enable_scheduler": True,
                "scheduler_jobs_db": str(db_path),
                "scheduler_max_workers": 5,
                "scheduler_coalesce": True,
                "scheduler_max_instances": 1,
                "scheduler_timezone": "Asia/Shanghai",
                "morning_greeting_hour": 9,
                "morning_greeting_minute": 0,
                "morning_greeting_misfire_grace": 86400,
                "reminder_misfire_grace": 3600,
                "scheduler_monitoring": True,
            }
        )
        stop_scheduler()

        mock_scheduler_instance = MagicMock()
        mock_bg.return_value = mock_scheduler_instance

        start_scheduler()

        # 验证 BackgroundScheduler 使用 SQLAlchemyJobStore
        call_kwargs = mock_bg.call_args[1]
        assert "jobstores" in call_kwargs
        assert "executors" in call_kwargs
        assert "timezone" in call_kwargs
        assert call_kwargs["timezone"] == "Asia/Shanghai"

        # 验证早安问候注册
        mock_scheduler_instance.add_job.assert_any_call(
            ANY, trigger=ANY, id="morning_greeting",
            misfire_grace_time=86400, replace_existing=True,
        )

        # 验证事件监听器注册（monitoring=true）
        mock_scheduler_instance.add_listener.assert_called_once()

        # 验证启动
        mock_scheduler_instance.start.assert_called_once()

    @patch(_APS_BG)
    @patch(_APS_STORE)
    @patch(_APS_TP)
    def test_monitoring_disabled(self, mock_tp, mock_store, mock_bg,
                                  monkeypatch, tmp_path):
        """SCHEDULER_MONITORING=false 时不注册事件监听器。"""
        db_path = tmp_path / "jobs.sqlite"
        monkeypatch.setattr(
            "src.core.scheduler.get_settings",
            lambda: {
                "enable_scheduler": True,
                "scheduler_jobs_db": str(db_path),
                "scheduler_max_workers": 5,
                "scheduler_coalesce": True,
                "scheduler_max_instances": 1,
                "scheduler_timezone": "UTC",
                "morning_greeting_hour": 8,
                "morning_greeting_minute": 30,
                "morning_greeting_misfire_grace": 7200,
                "reminder_misfire_grace": 0,
                "scheduler_monitoring": False,
            }
        )
        stop_scheduler()

        mock_scheduler_instance = MagicMock()
        mock_bg.return_value = mock_scheduler_instance

        start_scheduler()

        # 验证早安问候使用配置的小时/分钟
        mock_scheduler_instance.add_job.assert_any_call(
            ANY, trigger=ANY, id="morning_greeting",
            misfire_grace_time=7200, replace_existing=True,
        )

        # 验证不注册事件监听器
        mock_scheduler_instance.add_listener.assert_not_called()


# ── 提醒注册 ──────────────────────────────────────────────

class TestRegisterReminder:
    """测试 register_reminder 持久态提醒注册。"""

    @patch(_APS_BG)
    @patch(_APS_STORE)
    @patch(_APS_TP)
    def test_reminder_with_misfire_grace(self, mock_tp, mock_store, mock_bg,
                                          monkeypatch, tmp_path):
        """提醒注册应带上 misfire_grace_time。"""
        db_path = tmp_path / "jobs.sqlite"
        monkeypatch.setattr(
            "src.core.scheduler.get_settings",
            lambda: {
                "enable_scheduler": True,
                "scheduler_jobs_db": str(db_path),
                "scheduler_max_workers": 5,
                "scheduler_coalesce": True,
                "scheduler_max_instances": 1,
                "scheduler_timezone": "Asia/Shanghai",
                "morning_greeting_hour": 9,
                "morning_greeting_minute": 0,
                "morning_greeting_misfire_grace": 86400,
                "reminder_misfire_grace": 1800,
                "scheduler_monitoring": False,
            }
        )
        stop_scheduler()

        mock_scheduler_instance = MagicMock()
        mock_bg.return_value = mock_scheduler_instance

        start_scheduler()

        reminder_time = datetime(2026, 6, 28, 14, 30)
        register_reminder("明天下午2点半开会", reminder_time)

        # 验证提醒 job 包含 misfire_grace_time=1800
        reminder_calls = [
            c for c in mock_scheduler_instance.add_job.call_args_list
            if "reminder_" in str(c)
        ]
        assert len(reminder_calls) >= 1
        reminder_call = reminder_calls[0]
        assert reminder_call[1].get("misfire_grace_time") == 1800
        assert reminder_call[1].get("replace_existing") is True

    def test_noop_when_scheduler_none(self):
        """_scheduler=None 时 register_reminder 不抛异常。"""
        import src.core.scheduler as sched
        sched._scheduler = None
        # 不应抛异常
        register_reminder("test", datetime.now() + timedelta(hours=1))


# ── 待处理提醒 ────────────────────────────────────────────

class TestGetPendingReminders:
    """测试 get_pending_reminders。"""

    def test_returns_empty_when_no_scheduler(self):
        import src.core.scheduler as sched
        sched._scheduler = None
        result = get_pending_reminders()
        assert result == []


# ── 提醒回调注入队列 ────────────────────────────────────

class TestReminderCallback:
    """测试提醒回调注入队列。"""

    def test_callback_pushes_to_queue(self):
        """_default_reminder_callback 向 _reminder_queue 推送带前缀的消息。"""
        import queue
        q = queue.Queue()
        set_reminder_queue(q)
        _default_reminder_callback("说爱我")
        msg = q.get_nowait()
        assert msg == "__reminder__说爱我"

    def test_callback_logs_when_no_queue(self):
        """无队列时回调用 add_log 记录提醒。"""
        import src.core.scheduler as sched
        sched._reminder_queue = None
        from src.core.scheduler import _log_buffer, get_logs
        _log_buffer.clear()
        _default_reminder_callback("说爱我")
        logs = get_logs(limit=5)
        assert any("说爱我" in l["message"] for l in logs)
