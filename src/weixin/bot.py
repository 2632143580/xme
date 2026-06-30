"""Bot 主循环 — 微信消息并发处理 + Agent 调用 + 回复发送。

核心设计（任务书 v2.3）:
  - 主循环: 长轮询 get_updates → 并发分发 _handle_message (asyncio.Task)
  - Agent 调用: 使用 app.astream()（异步上下文），区别于 CLI 的 app.stream()
  - 用户隔离: 通过 RunnableConfig.configurable 注入 wx_user_id（路径 A）
              降级方案: 存储层 graph.py/client.py 已内置 uid 参数（路径 B）
  - 回复管道: sendTyping(status=1) → astream Agent → sendMessage → sendTyping(status=2)
  - 限流退避: sendMessage ret==-2 时指数退避重试（最多 3 次）
  - Token 过期: getUpdates ret!=0 + errcode -14/-15 → 触发重新登录
  - buf 持久化: 每次 get_updates 后立即写文件
  - 配置读取: 统一使用 get_settings()（禁止 os.environ）
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Optional

import httpx

from src.config import get_settings
from src.weixin.channel import (
    get_updates,
    send_message,
    send_typing,
    get_config,
    extract_text,
    is_bot_message,
    check_token_error,
    is_rate_limited,
)
from src.weixin.auth import login, load_credentials, save_credentials, LoginCredentials

logger = logging.getLogger(__name__)

# ── 持久化文件路径 ────────────────────────────────────────────────

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
BUF_FILE = os.path.join(DATA_DIR, "wx_buf.json")


class WeixinBot:
    """微信 Bot 主类。

    Usage::
        bot = WeixinBot()
        await bot.run()   # 阻塞运行直到 shutdown
    """

    def __init__(self) -> None:
        self.credentials: LoginCredentials | None = None
        self.buf: str = ""                              # get_updates 游标
        self.context_tokens: dict[str, str] = {}         # user_id → context_token 映射
        self.running: bool = False
        self._concurrent_tasks: set[asyncio.Task] = set()
        self.typing_ticket: str | None = None             # getConfig 返回的 ticket
        self.ilink_user_id: str | None = None             # 来自 getConfig / 凭证
        self._client: httpx.AsyncClient | None = None

    # ── 生命周期 ──────────────────────────────────────────────────

    async def run(self) -> None:
        """启动 Bot（入口方法）。"""
        self.running = True
        timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            self._client = client
            try:
                await self._startup(client)
                await self._main_loop(client)
            except KeyboardInterrupt:
                print("\n[wx] 收到中断信号，正在关闭...")
            finally:
                await self._shutdown()

    async def _startup(self, client: httpx.AsyncClient) -> None:
        """启动流程: 登录 → 加载 buf → 获取 typing_ticket。"""
        # 1. 登录
        self.credentials = await login(client)
        if not self.credentials or not self.credentials.is_valid:
            raise RuntimeError("[wx] 启动失败: 无法获取有效凭证")

        self.ilink_user_id = self.credentials.ilink_user_id

        # 2. 恢复游标
        self._load_buf()

        # 3. 获取 typing_ticket
        await self._refresh_typing_ticket(client)

        print("[wx] ✓ 微信 Bot 已就绪")

    async def _shutdown(self) -> None:
        """关闭流程: 持久化 buf → 取消 pending tasks。"""
        self.running = False
        self._persist_buf()

        # 取消所有进行中的任务
        for task in list(self._concurrent_tasks):
            task.cancel()
        if self._concurrent_tasks:
            results = await asyncio.gather(*self._concurrent_tasks, return_exceptions=True)
            cancelled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
            if cancelled:
                logger.info("[wx] 已取消 %d 个未完成任务", cancelled)

        print("[wx] Bot 已关闭")

    # ── 主循环 ────────────────────────────────────────────────────

    async def _sleep_check_running(self, seconds: float) -> bool:
        """休眠 seconds 秒，每 0.5s 检查 self.running。

        Returns True 如果正常结束，False 如果被 shutdown 中断。
        """
        steps = int(seconds / 0.5)
        for _ in range(steps):
            if not self.running:
                return False
            await asyncio.sleep(0.5)
        return True

    async def _main_loop(self, client: httpx.AsyncClient) -> None:
        """长轮询主循环。

        核心逻辑:
          1. get_updates(token, buf, timeout)
          2. 检查 ret + errcode（token 过期则重登）
          3. 更新 buf 并持久化
          4. 并发分发每条消息（asyncio.Task）
        """
        s = get_settings()
        poll_timeout = int(s.get("wx_poll_timeout", "35"))

        while self.running:
            try:
                if not self.credentials or not self.credentials.token:
                    logger.warning("[wx] 无凭证，尝试重新登录...")
                    self.credentials = await login(client, force_relogin=True)
                    continue

                resp = await get_updates(
                    client, self.credentials.token, self.buf, timeout=poll_timeout
                )

                # ⚠️ 先检查 ret 和 errcode
                ret = resp.get("ret", 0)
                if ret != 0:
                    if check_token_error(resp):
                        # Token 过期 → 重新登录
                        print("[wx] Token 过期，正在重新登录...")
                        self.credentials = await login(client, force_relogin=True)
                        continue
                    else:
                        # 其他错误，可中断等待后继续
                        if not await self._sleep_check_running(5):
                            break
                        continue

                # 更新游标
                new_buf = resp.get("get_updates_buf", self.buf)
                if new_buf:
                    self.buf = new_buf
                    self._persist_buf()

                # 分发消息
                msgs = resp.get("msgs", [])
                for msg in msgs:
                    if not self.running:
                        break

                    # 丢弃 BOT 自身回声
                    if is_bot_message(msg):
                        logger.debug("[wx] 丢弃 BOT 回声: %s", msg.get("from_user_id"))
                        continue

                    # 并发处理
                    task = asyncio.create_task(
                        self._handle_message(client, msg), name=f"handle_{msg.get('from_user_id', '?')}"
                    )
                    self._concurrent_tasks.add(task)
                    task.add_done_callback(self._concurrent_tasks.discard)

            except httpx.TimeoutException:
                # 长轮询超时是正常现象
                logger.debug("[wx] 长轮询超时，继续...")
                continue
            except httpx.HTTPStatusError as e:
                logger.error("[wx] HTTP 错误: %s %s", e.response.status_code, e)
                if not await self._sleep_check_running(5):
                    break
            except Exception as e:
                logger.error("[wx] 主循环异常: %s", e, exc_info=True)
                if not await self._sleep_check_running(5):
                    break

    # ── 消息处理管道 ───────────────────────────────────────────────

    async def _handle_message(
        self, client: httpx.AsyncClient, msg: dict
    ) -> None:
        """单条消息的完整处理管道。

        流程:
          1. 提取文本 + 用户 ID + context_token
          2. 发送「正在输入」(sendTyping status=1)
          3. 调用 Agent (astream)
          4. 发送回复 (sendMessage, 含限流退避)
          5. 发送「取消输入」(sendTyping status=2)
        """
        user_id = msg.get("from_user_id", "unknown")

        try:
            # 丢弃 BOT 回声（双重保险）
            if is_bot_message(msg):
                return

            text = extract_text(msg)
            if not text.strip():
                return

            ctx = msg.get("context_token", "")
            if ctx:
                self.context_tokens[user_id] = ctx

            logger.info("[wx] 收到消息 user=%s: %.80s", user_id, text)

            # 发送「正在输入」
            await self._send_typing_if_available(client, status=1)

            # 调用 Agent
            reply_text = await self._call_agent(user_id, text)

            # 发送回复（含限流退避）
            reply_ctx = self.context_tokens.get(user_id, "")
            await self._send_reply(client, user_id, reply_text, reply_ctx)

            # 发送「取消输入」
            await self._send_typing_if_available(client, status=2)

        except Exception as e:
            logger.error("[wx] 消息处理异常 (user=%s): %s", user_id, e, exc_info=True)

    async def _call_agent(self, user_id: str, text: str) -> str:
        """调用 LangGraph Agent（异步 astream）。

        ⚠️ v2.3 关键: wx bot 运行在 asyncio 上下文中，必须用 app.astream()
           （CLI 模式用同步 app.stream()，见 main.py 第 132-136 行）

        用户隔离 路径B: 通过 contextvars 传递 user_id（比 LangChain RunnableConfig
                   更可靠 — ToolNode 不保证传播 config）。
        """
        from src.core.agent import app
        from langchain_core.messages import HumanMessage
        from src.weixin.user_context import set_current_user, current_user_id

        config = {
            "configurable": {
                "thread_id": f"wx_{user_id}",
            }
        }

        # 路径B: contextvar 注入，工具内部自动读取
        token = set_current_user(user_id)
        try:
            final_content = ""
            try:
                async for event in app.astream(
                    {"messages": [HumanMessage(content=text)]},
                    config,
                    stream_mode="values",
                ):
                    messages = event.get("messages", [])
                    if messages:
                        last = messages[-1]
                        if hasattr(last, "content") and last.content:
                            final_content = last.content
            except Exception as e:
                logger.error("[wx] Agent 调用异常 (user=%s): %s", user_id, e)
                final_content = "（抱歉，处理您的消息时出错了，请稍后重试）"
        finally:
            current_user_id.reset(token)

        return final_content or "（暂无回复）"

    async def _send_reply(
        self,
        client: httpx.AsyncClient,
        user_id: str,
        text: str,
        context_token: str = "",
    ) -> None:
        """发送回复消息（含限流退避）。

        ⚠️ v2.2: ret==-2 时指数退避重试（最多 3 次）
        """
        if not self.credentials:
            return

        max_retries = 3
        for attempt in range(max_retries):
            resp = await send_message(
                client,
                token=self.credentials.token,
                user_id=user_id,
                text=text,
                context_token=context_token,
            )
            ret = resp.get("ret", 0)
            if ret == 0:
                logger.info("[wx] ✓ 回复已发送 user=%s (%d字)", user_id, len(text))
                return
            elif is_rate_limited(resp):
                wait = 2 ** attempt  # 指数退避: 1s → 2s → 4s
                logger.warning(
                    "[wx] 限流(ret=-2), %ds后重试(%d/%d) user=%s",
                    wait, attempt + 1, max_retries, user_id,
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "[wx] 发送失败(ret=%d) user=%s", ret, user_id
                )
                return
        else:
            logger.error("[wx] 重试%d次均失败 user=%s", max_retries, user_id)

    async def _send_typing_if_available(
        self, client: httpx.AsyncClient, status: int = 1
    ) -> None:
        """条件性发送正在输入/取消输入（ticket 不可用时静默跳过）。"""
        if not self.credentials or not self.typing_ticket or not self.ilink_user_id:
            return
        try:
            await send_typing(
                client,
                token=self.credentials.token,
                ilink_user_id=self.ilink_user_id,
                typing_ticket=self.typing_ticket,
                status=status,
            )
        except Exception as e:
            logger.debug("[wx] sendTyping 失败(status=%d): %s", status, e)

    async def _refresh_typing_ticket(self, client: httpx.AsyncClient) -> None:
        """刷新 typing_ticket（启动时调用一次，后续可定时刷新）。"""
        if not self.credentials or not self.ilink_user_id:
            return
        try:
            resp = await get_config(
                client,
                token=self.credentials.token,
                ilink_user_id=self.ilink_user_id,
            )
            if resp.get("ret", 0) == 0:
                self.typing_ticket = resp.get("typing_ticket")
                uid = resp.get("ilink_user_id")
                if uid:
                    self.ilink_user_id = uid
                logger.info("[wx] typing_ticket 已刷新")
            else:
                logger.warning("[wx] getConfig 返回 ret=%s", resp.get("ret"))
        except Exception as e:
            logger.warning("[wx] 刷新 typing_ticket 失败: %s", e)

    # ── buf 持久化 ────────────────────────────────────────────────

    def _persist_buf(self) -> None:
        """将 get_updates 游标写入文件（重启后可恢复，避免丢消息）。"""
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            data = {"buf": self.buf, "saved_at": time.time()}
            with open(BUF_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning("[wx] buf 持久化失败: %s", e)

    def _load_buf(self) -> None:
        """从文件恢复游标。"""
        if not os.path.exists(BUF_FILE):
            return
        try:
            with open(BUF_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.buf = data.get("buf", "")
            logger.info("[wx] 已恢复游标 buf=%.20s...", self.buf)
        except Exception as e:
            logger.warning("[wx] buf 恢复失败: %s", e)

    # ── 重新登录 ──────────────────────────────────────────────────

    async def _relogin(self, client: httpx.AsyncClient) -> None:
        """Token 过期时触发的重新登录流程。"""
        print("[wx] Token 过期，正在重新登录...")
        self.credentials = await login(client, force_relogin=True)
        if self.credentials:
            self.ilink_user_id = self.credentials.ilink_user_id
            await self._refresh_typing_ticket(client)
            print("[wx] ✓ 重新登录成功")


# ── 便捷入口 ──────────────────────────────────────────────────────

async def run_bot() -> None:
    """便捷入口: 创建并运行 Bot。"""
    bot = WeixinBot()
    await bot.run()


def main() -> None:
    """同步入口（供 start.py wx 模式调用）。"""
    print("=" * 50)
    print("  小知 - 微信 Bot 模式")
    print("=" * 50)

    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
