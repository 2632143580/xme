"""FastAPI 后端服务 -- 小知前端控制台的 REST API + SSE 推送。

启动: python -m src.api.server
端口: 默认 8000，可通过 API_PORT 环境变量修改
"""
import os
import sys
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
import json
from langchain_core.messages import HumanMessage

# 确保 demo 项目根目录在 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
load_dotenv()

from src.config import get_settings, write_env, mask_secret, _ENV_KEY_MAP, _SECRET_KEYS, ENV_FILE
from src.tools.note_tools import get_client
from src.core.agent import app as agent_app
from src.core.scheduler import (
    start_scheduler, stop_scheduler, should_proactively_engage,
    record_user_activity, get_idle_minutes, get_pending_reminders,
    extract_reminder_time, register_reminder, remove_reminder,
    set_reminder_queue, get_logs, register_event_callback,
    unregister_event_callback, add_log, get_scheduler_status,
    hot_update_greeting, hot_update_greeting_misfire,
    hot_update_idle_threshold, hot_update_scheduler,
    IDLE_THRESHOLD_MINUTES,
)
from src.memory.graph import query_user_graph, is_connected

# ── 启动时间追踪 ─────────────────────────────────────────────
_start_time = datetime.now()

# ── 热更新参数列表（LLM 已懒加载，改模型/供应商都无需重启）
HOT_UPDATE_KEYS = {
    # 调度器
    "MORNING_GREETING_HOUR", "MORNING_GREETING_MINUTE",
    "MORNING_GREETING_MISFIRE_GRACE", "IDLE_THRESHOLD_MINUTES",
    "ENABLE_SCHEDULER",
    # LLM（懒加载，下次请求自动生效）
    "LLM_PROVIDER",
    "VOLCENGINE_API_KEY", "VOLCENGINE_BASE_URL", "VOLCENGINE_MODEL",
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动/关闭调度器。"""
    start_scheduler()
    add_log("info", "API 服务已启动")
    yield
    unregister_event_callback(_sse_push)
    stop_scheduler()


api_app = FastAPI(title="小知控制台 API", version="1.0.0", lifespan=lifespan)

# 微信 Bot 子路由
from src.api.wx_api import router as wx_router
api_app.include_router(wx_router)

# CORS: 允许前端跨域
api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── SSE 事件队列 ─────────────────────────────────────────────
_sse_connections = []


def _sse_push(event: dict):
    """向所有 SSE 连接推送事件。"""
    for q in _sse_connections:
        try:
            q.put_nowait(event)
        except Exception:
            pass


# 注册 SSE 推送回调（scheduler 日志/提醒/问候事件）
register_event_callback(_sse_push)


# ── 生命周期管理（通过 lifespan 上下文，见上方）────────────────


# ══════════════════════════════════════════════════════════════
#  REST API 路由
# ══════════════════════════════════════════════════════════════

# ── POST /api/test-connection ──────────────────────────────────

@api_app.post("/api/test-connection")
async def test_connection():
    """测试当前 LLM 连接：发一条 ping，返回耗时、模型名、状态。"""
    import time
    try:
        from src.llm_factory import get_llm
        from src.config import get_settings

        s = get_settings()
        provider = s.get("llm_provider", "unknown")
        model = s.get(f"{provider}_model", "")

        t0 = time.time()
        llm = get_llm(temperature=0)
        resp = await asyncio.to_thread(
            llm.invoke, [HumanMessage(content="ping")])
        elapsed = round((time.time() - t0) * 1000)

        return {
            "ok": True,
            "provider": provider,
            "model": model,
            "latency_ms": elapsed,
            "reply": resp.content[:100] if resp.content else "(空响应)",
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)[:200],
        }


# ══════════════════════════════════════════════════════════════

# ── GET /api/status ──────────────────────────────────────────

# ponytail: status endpoint has sync LLM ping (2-30s blocking).
# Production fix: wrap in run_in_executor. Skipped for test simplicity.

@api_app.get("/api/status")
async def get_status():
    """返回系统全部运行状态。"""
    client = get_client()
    s = get_settings()

    stats = {}
    try:
        stats["dialogues"] = client.conn.execute(
            "SELECT COUNT(*) FROM conversations").fetchone()[0]
        stats["notes"] = client.conn.execute(
            "SELECT COUNT(*) FROM notes").fetchone()[0]
        stats["summaries"] = client.conn.execute(
            "SELECT COUNT(*) FROM summaries").fetchone()[0]
    except Exception:
        stats = {"dialogues": 0, "notes": 0, "summaries": 0}

    vector_count = 0
    if client.qdrant is not None:
        try:
            info = client.qdrant.get_collection(client._qdrant_collection)
            vector_count = info.points_count
        except Exception:
            vector_count = 0

    embedding_loaded = False
    try:
        from src.memory.embedding import get_embedder
        emb = get_embedder()
        embedding_loaded = emb is not None
    except Exception:
        embedding_loaded = False

    llm_status = "unknown"
    try:
        from src.llm_factory import get_llm
        llm = get_llm(temperature=0)
        resp = await asyncio.to_thread(
            llm.invoke, [HumanMessage(content="ping")])
        llm_status = "connected" if resp.content else "error"
    except Exception:
        llm_status = "error"

    graph_data = query_user_graph() if is_connected() else {}

    # 映射 connections 为枚举字符串
    def _conn(v):
        if v is True:
            return "connected"
        if v is False:
            return "down"
        if v == "connected":
            return "connected"
        if v == "connecting":
            return "connecting"
        return "down"

    return {
        "running": True,
        "bot_id": s.get("bot_id", ""),
        "user_id": s.get("user_id", ""),
        "uptime": int((datetime.now() - _start_time).total_seconds()),
        "idle": int(get_idle_minutes() * 60) if get_idle_minutes() else 0,
        "connections": {
            "qdrant": _conn(client.qdrant is not None),
            "neo4j": _conn(is_connected()),
            "llm": _conn(llm_status),
        },
        "stats": {
            "dialogues": stats.get("dialogues", 0),
            "notes": stats.get("notes", 0),
            "vectors": vector_count,
        },
        "graph": {
            "preferences": len(graph_data.get("preferences", [])),
            "events": len(graph_data.get("events", [])),
            "people": len(graph_data.get("people", [])),
        },
    }


# ── GET /api/config ─────────────────────────────────────────

@api_app.get("/api/config")
async def get_config():
    """返回所有 .env 参数，API Key 脱敏。"""
    s = get_settings()
    result = {}
    for py_key, env_var in _ENV_KEY_MAP.items():
        value = s.get(py_key, "")
        # 脱敏
        if py_key in _SECRET_KEYS:
            display_value = mask_secret(str(value))
        else:
            display_value = value if isinstance(value, (int, float, bool)) else str(value)
        result[env_var] = {
            "value": display_value,
            "raw_type": type(value).__name__,
            "hot_update": env_var in HOT_UPDATE_KEYS,
        }
    return result


# ── PUT /api/config ─────────────────────────────────────────

@api_app.put("/api/config")
async def update_config(updates: dict):
    """修改 .env 参数。热更新参数立即生效，其余需重启。"""
    updated_env_vars = []
    need_restart = False
    restart_hint = ""

    # 转换：前端传 env_var_name，需映射到 .env
    env_updates = {}
    for env_var, new_value in updates.items():
        env_updates[env_var] = str(new_value)

    # 写 .env
    updated_keys = write_env(env_updates)
    updated_env_vars = updated_keys

    # 热更新
    for env_var in updated_keys:
        if env_var not in HOT_UPDATE_KEYS:
            need_restart = True
            restart_hint = "以下参数修改需重启生效"
            continue

        # 逐一热更新
        if env_var == "MORNING_GREETING_HOUR":
            hour = int(updates[env_var])
            minute = int(updates.get("MORNING_GREETING_MINUTE",
                           str(get_settings()["morning_greeting_minute"])))
            hot_update_greeting(hour, minute)
        elif env_var == "MORNING_GREETING_MINUTE":
            hour = int(updates.get("MORNING_GREETING_HOUR",
                           str(get_settings()["morning_greeting_hour"])))
            minute = int(updates[env_var])
            hot_update_greeting(hour, minute)
        elif env_var == "MORNING_GREETING_MISFIRE_GRACE":
            hot_update_greeting_misfire(int(updates[env_var]))
        elif env_var == "IDLE_THRESHOLD_MINUTES":
            hot_update_idle_threshold(int(updates[env_var]))
        elif env_var == "ENABLE_SCHEDULER":
            hot_update_scheduler(str(updates[env_var]).lower() == "true")

    # 清除 get_settings 缓存，下次请求重新读取
    # write_env 内部已做 cache_clear + load_dotenv
    get_settings.cache_clear()
    add_log("info", f"配置已更新: {updated_env_vars}")

    # SSE 推送配置变更
    _sse_push({"type": "config", "data": {"updated": updated_env_vars,
               "need_restart": need_restart}})

    return {
        "updated": updated_env_vars,
        "need_restart": need_restart,
        "restart_hint": restart_hint if need_restart else "",
    }


# ── GET /api/reminders ──────────────────────────────────────

@api_app.get("/api/reminders")
async def get_reminders():
    """返回待触发提醒列表。"""
    return get_pending_reminders(limit_minutes=60)


# ── POST /api/reminders ─────────────────────────────────────

@api_app.post("/api/reminders")
async def create_reminder(data: dict):
    """创建提醒。body: { content: str, time: ISO8601 datetime }"""
    content = data.get("content", "")
    time_str = data.get("time", "")

    if not content or not time_str:
        raise HTTPException(400, "content 和 time 必填")

    try:
        reminder_time = datetime.fromisoformat(time_str)
    except Exception:
        raise HTTPException(400, "time 格式错误，需 ISO8601")

    if reminder_time <= datetime.now():
        raise HTTPException(400, "提醒时间必须在未来")

    register_reminder(content, reminder_time)
    return {"content": content, "due_time": reminder_time.isoformat()}


# ── DELETE /api/reminders/:id ────────────────────────────────

@api_app.delete("/api/reminders/{job_id}")
async def delete_reminder(job_id: str):
    """删除提醒。"""
    success = remove_reminder(job_id)
    if not success:
        raise HTTPException(404, f"提醒 {job_id} 不存在或调度器未运行")
    return {"removed": True, "job_id": job_id}


# ── GET /api/dialogues ──────────────────────────────────────

@api_app.get("/api/dialogues")
async def get_dialogues(limit: int = Query(default=20, ge=1, le=100)):
    """返回最近对话。"""
    client = get_client()
    return client.recent_dialogue(limit=limit)


# ── POST /api/message ───────────────────────────────────────

@api_app.post("/api/message")
async def send_message(data: dict):
    """发消息走 Agent 对话流程。body: { content: str }

    ponytail: 当前同步阻塞模式（stream 完整收集后返回）。
    如需 SSE 流式逐 token，需将 stream 迭代拆到主循环 + run_in_executor。
    """
    content = data.get("content", "")
    if not content:
        raise HTTPException(400, "content 必填")

    record_user_activity()

    # 检查时间意图
    reminder_time = extract_reminder_time(content)
    reminder_info = None
    if reminder_time:
        register_reminder(content, reminder_time)
        reminder_info = {
            "content": content,
            "due_time": reminder_time.isoformat(),
        }

    # 保存用户消息
    client = get_client()
    client.save_dialogue("user", content)

    # 调用 Agent
    # ponytail: 同步阻塞模式，LLM hang 时请求永久挂起。
    # 生产环境建议 asyncio.wait_for + run_in_executor(timeout=120）。
    config = {"configurable": {"thread_id": "user1"}}
    try:
        def _run_agent():
            final = None
            for event in agent_app.stream(
                {"messages": [HumanMessage(content=content)]},
                config, stream_mode="values"
            ):
                final = event
            return final
        final = await asyncio.to_thread(_run_agent)

        reply = ""
        tool_calls = []
        if final and final.get("messages"):
            last = final["messages"][-1]
            reply = getattr(last, "content", "")
            if hasattr(last, "tool_calls") and last.tool_calls:
                tool_calls = [
                    {"name": tc["name"], "args": tc.get("args", {})}
                    for tc in last.tool_calls
                ]

        # 图谱可能已变更，推送最新图谱数据（对话由 HTTP 响应返回，不 SSE 重复推送）
        _sse_push({"type": "graph", "data": query_user_graph()})

        return {"reply": reply, "tool_calls": tool_calls,
                "reminder": reminder_info}

    except Exception as e:
        add_log("error", f"Agent 调用失败: {e}")
        raise HTTPException(500, f"对话出错: {e}")


# ── GET /api/graph ──────────────────────────────────────────

@api_app.get("/api/graph")
async def get_graph():
    """返回知识图谱摘要。"""
    graph_data = query_user_graph()
    if not graph_data:
        return {"preferences": [], "events": [], "people": []}
    return graph_data


# ── GET /api/logs ───────────────────────────────────────────

@api_app.get("/api/logs")
async def get_log_entries(limit: int = Query(default=30, ge=1, le=100)):
    """返回最近日志（最新在前）。"""
    return get_logs(limit=limit)


# ── GET /api/events (SSE) ───────────────────────────────────

@api_app.get("/api/events")
async def sse_events():
    """SSE 实时推送: dialogue / reminder / log / config / graph 事件。"""
    async def event_generator():
        q = asyncio.Queue(maxsize=100)
        _sse_connections.append(q)
        try:
            while True:
                event = await q.get()
                data_str = json.dumps(event.get("data", ""), ensure_ascii=False)
                yield {
                    "event": event.get("type", "message"),
                    "data": data_str,
                }
        finally:
            if q in _sse_connections:
                _sse_connections.remove(q)

    return EventSourceResponse(event_generator())


# ── 前端静态文件 ──────────────────────────────────────────────
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "frontend")

if os.path.isdir(_frontend_dir) and os.path.isfile(os.path.join(_frontend_dir, "index.html")):
    # ⚠️ 不能用 api_app.mount("/", StaticFiles("/")) —— StaticFiles 会拦截所有请求，
    #    导致 /api/weixin/* 路由返回 405。改用显式路由。
    from starlette.staticfiles import StaticFiles as _StarletteStaticFiles

    # 为静态资源（css/js/图片等）创建一个子挂载
    _static_app = _StarletteStaticFiles(directory=_frontend_dir, html=True)

    @api_app.get("/")
    async def _serve_index():
        """根路径显式返回 index.html。"""
        return FileResponse(os.path.join(_frontend_dir, "index.html"))

    @api_app.get("/{full_path:path}")
    async def _serve_frontend(full_path: str):
        """前端静态资源 + SPA fallback。
        所有非 API 路径的 GET 请求走这里，优先返回物理文件，否则返回 index.html。
        """
        file_path = os.path.join(_frontend_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        # SPA fallback: 客户端路由（如 /status /config）统一返回 index.html
        return FileResponse(os.path.join(_frontend_dir, "index.html"))


def run_server(port: int = None):
    """启动 uvicorn 服务器。"""
    import uvicorn
    port = port or int(os.getenv("API_PORT", "8000"))
    uvicorn.run(api_app, host="0.0.0.0", port=port, log_level="info")


# 暴露 _last_user_msg_time 以供 status 查询
from src.core.scheduler import _last_user_msg_time


if __name__ == "__main__":
    run_server()
