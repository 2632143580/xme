"""主动调度 -- APScheduler 持久态调度器 + 定时问候 + 到点提醒 + 空闲检测。

架构升级（v5 优化版）:
  持久层: SQLAlchemyJobStore -> jobs.sqlite，重启自动重载
  补执行层: misfire_grace_time + coalesce=True，宽限期内补跑不重复
  线程池: 显式 ThreadPoolExecutor，防默认 10 线程占满丢任务
  监听器: 捕获丢任务/异常事件，日志可查
  日志缓冲: deque maxlen=200，SSE 推送 + REST 查询
  热更新: 5 个参数可在线修改不重启进程
"""
import os
import re
import warnings
import queue
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

from src.config import get_settings


import threading

_scheduler = None
_last_user_msg_time: Optional[datetime] = None
_reminder_queue: "queue.Queue" = None  # 主循环注入，提醒回调向此推送消息
_state_lock = threading.Lock()
IDLE_THRESHOLD_MINUTES = 30

# ── 日志环形缓冲区（SSE 推送 + REST 查询）─────────────────────
_log_buffer = deque(maxlen=200)
_event_callbacks = []  # SSE 推送回调列表
_callbacks_lock = threading.Lock()


def add_log(level: str, message: str):
    """写入日志缓冲区 + 触发 SSE 推送。"""
    entry = {
        "level": level,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }
    _log_buffer.append(entry)
    for cb in _event_callbacks:
        try:
            cb({"type": "log", "data": entry})
        except Exception:
            pass


def get_logs(limit: int = 30) -> list:
    """返回最近 N 条日志（最新在前）。"""
    items = list(_log_buffer)[-limit:]
    items.reverse()
    return items


def register_event_callback(cb):
    """注册 SSE 推送回调。API server 使用。"""
    with _callbacks_lock:
        _event_callbacks.append(cb)


def unregister_event_callback(cb):
    """移除 SSE 推送回调。"""
    with _callbacks_lock:
        if cb in _event_callbacks:
            _event_callbacks.remove(cb)


# ── 时间意图提取 ──────────────────────────────────────────

_WEEKDAY_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "天": 7, "日": 7, "末": 7}


def _adjust_hour(hour: int, period: Optional[str]) -> int:
    """上午/下午/晚上 等 12 小时制修正。"""
    if period in ("下午", "傍晚", "晚上"):
        return hour + 12 if hour < 12 else hour
    if period in ("上午", "早上"):
        return hour if hour != 12 else 0
    return hour


def _parse_relative_day(match, now: datetime) -> Optional[datetime]:
    day_word = match.group(1)
    period = match.group(2)
    hour = int(match.group(3))
    minute = int(match.group(4) or 0)
    hour = _adjust_hour(hour, period)
    delta = 1 if day_word == "明天" else 2
    target = now + timedelta(days=delta, hours=0)
    return target.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _parse_today_time(match, now: datetime) -> Optional[datetime]:
    period = match.group(1)
    hour = int(match.group(2))
    minute = 30 if "半" in match.group(0) else 0
    hour = _adjust_hour(hour, period)
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _parse_next_weekday(match, now: datetime) -> Optional[datetime]:
    weekday = _WEEKDAY_MAP.get(match.group(1))
    period = match.group(2)
    hour = int(match.group(3))
    minute = int(match.group(4) or 0)
    hour = _adjust_hour(hour, period)
    if weekday is None:
        return None
    days_ahead = weekday - now.isoweekday()
    if days_ahead <= 0:
        days_ahead += 7
    target = now + timedelta(days=days_ahead)
    return target.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _parse_relative_duration(match, now: datetime) -> Optional[datetime]:
    """解析 '10秒后' / '5分钟后' / '1小时后' 等相对时长。"""
    num = int(match.group(1))
    unit = match.group(2)
    if unit in ("秒", "s", "sec", "secs"):
        return now + timedelta(seconds=num)
    if unit in ("分", "分钟", "min", "mins", "m"):
        return now + timedelta(minutes=num)
    if unit in ("时", "小时", "hr", "hrs", "h"):
        return now + timedelta(hours=num)
    return None


_TIME_PATTERNS = [
    (re.compile(r"(\d+)\s*(秒|s|sec|mins?|分|分钟|m|时|小时|hrs?|h)\s*后?", re.IGNORECASE),
     _parse_relative_duration),
    (re.compile(r"下周([一二三四五六七末天日])\s*(上午|下午|晚上|早上)?\s*(\d{1,2})[点时](\d{0,2})?", re.UNICODE),
     _parse_next_weekday),
    (re.compile(r"(明天|后天)\s*(上午|下午|晚上|早上|傍晚)?\s*(\d{1,2})[点时](\d{0,2})?", re.UNICODE),
     _parse_relative_day),
    (re.compile(r"(上午|下午|晚上|早上|傍晚)?\s*(\d{1,2})[点时]半?", re.UNICODE),
     _parse_today_time),
]


def extract_reminder_time(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """从文本提取时间意图，返回目标 datetime。"""
    now = now or datetime.now()
    for pattern, parser in _TIME_PATTERNS:
        match = pattern.search(text)
        if match:
            result = parser(match, now)
            if result and result > now:
                return result
    return None


# ── 主动对话判断 ──────────────────────────────────────────

def should_proactively_engage(context: dict) -> tuple[bool, str]:
    """判断当前是否应主动发起对话。"""
    idle = context.get("idle_minutes", 0)
    pending = context.get("pending_reminders", [])

    for reminder in pending:
        if reminder.get("due_soon"):
            return True, f"提醒: {reminder.get('content', '')}"

    if idle >= IDLE_THRESHOLD_MINUTES:
        hour = int(context.get("current_time", "0:0").split(":")[0])
        if 6 <= hour < 12:
            return True, "早上好，有什么想聊的吗？"
        elif 12 <= hour < 18:
            return True, "下午了，要不要休息一下？"
        elif 18 <= hour < 23:
            return True, "晚上好，今天过得怎么样？"
        else:
            return True, "还在忙吗？注意休息。"

    return False, ""


# ── 调度器管理 ─────────────────────────────────────────────

def set_reminder_queue(q: "queue.Queue"):
    """主循环注入提醒消息队列，让回调消息进入对话循环。"""
    global _reminder_queue
    _reminder_queue = q


def _ensure_data_dir(db_path: str):
    """确保 job 持久化目录存在。"""
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)


def start_scheduler(callback: Optional[callable] = None):
    """启动 APScheduler 持久态后台调度器。"""
    s = get_settings()
    if not s.get("enable_scheduler", False):
        add_log("info", "主动调度已关闭（ENABLE_SCHEDULER=false）")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.executors.pool import ThreadPoolExecutor
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.events import EVENT_JOB_MISSED, EVENT_JOB_ERROR

        jobs_db = s["scheduler_jobs_db"]
        _ensure_data_dir(jobs_db)
        jobstore = SQLAlchemyJobStore(url=f"sqlite:///{jobs_db}")

        max_workers = s["scheduler_max_workers"]
        executors = {"default": ThreadPoolExecutor(max_workers)}

        job_defaults = {
            "coalesce": s["scheduler_coalesce"],
            "max_instances": s["scheduler_max_instances"],
        }

        global _scheduler
        _scheduler = BackgroundScheduler(
            jobstores={"default": jobstore},
            executors=executors,
            job_defaults=job_defaults,
            timezone=s["scheduler_timezone"],
        )

        greeting_hour = s["morning_greeting_hour"]
        greeting_minute = s["morning_greeting_minute"]
        misfire_greeting = s["morning_greeting_misfire_grace"]

        _scheduler.add_job(
            _morning_greeting,
            trigger=CronTrigger(hour=greeting_hour, minute=greeting_minute),
            id="morning_greeting",
            misfire_grace_time=misfire_greeting,
            replace_existing=True,
        )
        add_log("info", f"早安问候: 每天 {greeting_hour:02d}:{greeting_minute:02d}, "
                f"宽限期 {misfire_greeting}s")

        if s["scheduler_monitoring"]:
            def job_listener(event):
                if event.code == EVENT_JOB_MISSED:
                    add_log("warn", f"任务错过执行: {event.job_id}")
                elif event.code == EVENT_JOB_ERROR:
                    add_log("error", f"任务异常: {event.job_id} -> {event.exception}")

            _scheduler.add_listener(job_listener, EVENT_JOB_MISSED | EVENT_JOB_ERROR)
            add_log("info", "事件监听已启用")

        _scheduler.start()
        add_log("info", f"调度器已启动 (workers={max_workers}, "
                f"timezone={s['scheduler_timezone']}, db={jobs_db})")

    except ImportError:
        add_log("warn", "APScheduler 未安装，主动调度关闭")
    except Exception as e:
        add_log("error", f"调度器启动失败: {e}")


def stop_scheduler():
    """优雅关闭调度器。"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        add_log("info", "调度器已关闭")


def register_reminder(note_content: str, reminder_time: datetime,
                      callback: Optional[callable] = None):
    """注册一次性提醒 job。相同内容的提醒自动去重（replace）。"""
    if _scheduler is None:
        return

    try:
        from apscheduler.triggers.date import DateTrigger

        s = get_settings()
        misfire_reminder = s["reminder_misfire_grace"]
        cb = callback or _default_reminder_callback

        # 去重：检查是否有相同内容的待触发提醒，有则替换
        for job in _scheduler.get_jobs():
            if job.id.startswith("reminder_") and job.args and job.args[0] == note_content:
                remove_reminder(job.id)
                break

        _scheduler.add_job(
            cb,
            trigger=DateTrigger(run_date=reminder_time),
            args=[note_content],
            id=f"reminder_{reminder_time.isoformat()}",
            misfire_grace_time=misfire_reminder,
            replace_existing=True,
        )
        add_log("info", f"已注册提醒: {reminder_time.strftime('%Y-%m-%d %H:%M')} "
                f"(宽限期 {misfire_reminder}s)")
        # SSE 推送提醒注册事件
        for event_cb in _event_callbacks:
            try:
                event_cb({"type": "reminder", "data": {
                    "content": note_content,
                    "due_time": reminder_time.isoformat(),
                }})
            except Exception:
                pass
    except Exception as e:
        add_log("error", f"提醒注册失败: {e}")


def remove_reminder(job_id: str) -> bool:
    """删除提醒 job。"""
    if _scheduler is None:
        return False
    try:
        _scheduler.remove_job(job_id)
        add_log("info", f"已删除提醒: {job_id}")
        return True
    except Exception:
        return False


# ── 热更新接口（5 个参数可在线修改不重启）────────────────────

def hot_update_greeting(hour: int, minute: int) -> bool:
    """热更新早安问候时间。修改 CronTrigger 但不重启调度器。"""
    if _scheduler is None:
        return False
    try:
        from apscheduler.triggers.cron import CronTrigger
        _scheduler.modify_job(
            "morning_greeting",
            trigger=CronTrigger(hour=hour, minute=minute),
        )
        add_log("info", f"早安问候热更新为 {hour:02d}:{minute:02d}")
        return True
    except Exception as e:
        add_log("error", f"早安问候热更新失败: {e}")
        return False


def hot_update_greeting_misfire(misfire_grace: int) -> bool:
    """热更新早安问候宽限期。"""
    if _scheduler is None:
        return False
    try:
        _scheduler.modify_job(
            "morning_greeting",
            misfire_grace_time=misfire_grace,
        )
        add_log("info", f"早安宽限期热更新为 {misfire_grace}s")
        return True
    except Exception as e:
        add_log("error", f"早安宽限期热更新失败: {e}")
        return False


def hot_update_idle_threshold(threshold: int) -> bool:
    """热更新空闲阈值。"""
    global IDLE_THRESHOLD_MINUTES
    IDLE_THRESHOLD_MINUTES = threshold
    add_log("info", f"空闲阈值热更新为 {threshold} 分钟")
    return True


def hot_update_scheduler(enable: bool) -> bool:
    """热更新调度器开关。"""
    if enable and _scheduler is None:
        start_scheduler()
        add_log("info", "调度器热启动")
        return True
    if not enable and _scheduler is not None:
        stop_scheduler()
        add_log("info", "调度器热关闭")
        return True
    add_log("info", f"调度器状态未变 (enable={enable}, running={_scheduler is not None})")
    return True


# ── 内部回调 ────────────────────────────────────────────────

def _morning_greeting():
    """定时触发的早安问候。"""
    msg = "早上好！新的一天开始了，有什么计划吗？"
    add_log("info", msg)
    # SSE 推送问候事件
    for cb in _event_callbacks:
        try:
            cb({"type": "reminder", "data": {"content": msg}})
        except Exception:
            pass


def _default_reminder_callback(note_content: str):
    """提醒触发时的默认回调 -- 向主循环/SSE 推送提醒消息。"""
    # 去重：reminder 内容本身可能含 __reminder__ 前缀（防队列污染）
    clean_content = note_content
    while clean_content.startswith("__reminder__"):
        clean_content = clean_content[len("__reminder__"):]

    msg = f"到时间了！你之前让我提醒你：{clean_content}"

    # CLI 模式：推送到提醒队列（main.py 负责输出和持久化）
    if _reminder_queue is not None:
        _reminder_queue.put(f"__reminder__{clean_content}")
    else:
        add_log("info", f"提醒触发: {clean_content}")

    # API 模式：SSE 推送提醒事件（前端展示）+ 保存到对话库
    for cb in _event_callbacks:
        try:
            cb({"type": "reminder", "data": {
                "content": msg,
                "due_time": datetime.now().isoformat()
            }})
        except Exception:
            pass

    # API 模式：提醒也要持久化到对话（CLI 模式由 main.py 负责）
    if _reminder_queue is None:
        try:
            from src.tools.note_tools import get_client
            client = get_client()
            client.save_dialogue("assistant", msg)
        except Exception:
            pass


# ── 空闲追踪 ────────────────────────────────────────────────

def record_user_activity():
    """记录用户最近一次发言的时间。"""
    global _last_user_msg_time
    with _state_lock:
        _last_user_msg_time = datetime.now()


def get_idle_minutes() -> float:
    """返回自上次用户发言以来的空闲分钟数。"""
    global _last_user_msg_time
    with _state_lock:
        if _last_user_msg_time is None:
            return 0.0
        return (datetime.now() - _last_user_msg_time).total_seconds() / 60.0


def get_pending_reminders(limit_minutes: int = 10) -> list:
    """返回即将到期的提醒列表。"""
    if _scheduler is None:
        return []

    now = datetime.now()
    threshold = now + timedelta(minutes=limit_minutes)
    pending = []

    try:
        jobs = _scheduler.get_jobs()
        for job in jobs:
            if not job.id.startswith("reminder_"):
                continue
            nrt = job.next_run_time
            if nrt and nrt <= threshold:
                content = job.args[0] if job.args else ""
                due_soon = nrt <= now + timedelta(minutes=5)
                pending.append({
                    "job_id": job.id,
                    "content": content,
                    "trigger_at": nrt.isoformat() if nrt else "",
                })
    except Exception:
        pass

    return pending


def get_scheduler_status() -> dict:
    """返回调度器运行状态（供 API 查询）。"""
    running = _scheduler is not None
    jobs_info = []
    if running:
        try:
            for job in _scheduler.get_jobs():
                jobs_info.append({
                    "id": job.id,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                })
        except Exception:
            pass

    return {
        "running": running,
        "workers": get_settings()["scheduler_max_workers"] if running else 0,
        "timezone": get_settings()["scheduler_timezone"],
        "jobs": jobs_info,
    }
