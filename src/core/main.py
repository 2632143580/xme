"""CLI 入口 -- 交互式对话 + 主动调度。"""
import sys
import os
import time
import threading
import queue
import re
from datetime import datetime

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.agent import app
from src.tools.note_tools import get_client
from src.core.scheduler import (
    start_scheduler, should_proactively_engage,
    record_user_activity, get_idle_minutes, get_pending_reminders,
    extract_reminder_time, register_reminder, set_reminder_queue,
)

PROACTIVE_CHECK_INTERVAL = 30  # 秒
_last_proactive_msg = ""  # 上次主动发送的消息内容
_last_proactive_time = 0  # 上次主动发送的时间戳


def clean_text(text: str) -> str:
    """去除控制字符与零宽字符，保留所有语言文字。"""
    # 删除 C0/C1 控制字符 + 零宽字符（保留换行/制表）
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202f\ufeff]', '', text)


def main():
    global _last_proactive_msg, _last_proactive_time

    print("小知已就绪（输入 exit 退出）")
    # 仅当调度器未运行时启动（防与 API 进程双实例冲突）
    from src.core.scheduler import _scheduler
    if _scheduler is None:
        start_scheduler()

    config = {"configurable": {"thread_id": "user1"}}
    client = get_client()

    # 启动恢复
    try:
        state = app.get_state(config)
        n = len(state.values.get("messages", []))
        print(f"已恢复历史会话，消息数: {n}")
    except Exception:
        print("新会话开始")

    # 记录初始活跃时间
    record_user_activity()

    # 输入线程：阻塞读 stdin，丢进 queue
    input_q = queue.Queue()

    # 注入提醒队列：APScheduler 回调把提醒推入此队列
    set_reminder_queue(input_q)

    def input_loop():
        while True:
            try:
                line = input("\n你: ")
                input_q.put(line)
            except EOFError:
                input_q.put(None)
                break

    threading.Thread(target=input_loop, daemon=True).start()

    while True:
        # 先检查是否有提醒消息（非阻塞，优先处理）
        reminder_msg = None
        try:
            reminder_msg = input_q.get_nowait()
        except queue.Empty:
            pass

        if reminder_msg is not None:
            # 提醒消息直接输出，不走 Agent
            if isinstance(reminder_msg, str) and reminder_msg.startswith("__reminder__"):
                # 来自 APScheduler 回调的提醒，去重前缀
                content = reminder_msg
                while content.startswith("__reminder__"):
                    content = content[len("__reminder__"):]
                print(f"\n小知(提醒): {clean_text(content)}")
                client.save_dialogue("assistant", f"到时间了！你之前让我提醒你：{content}")
                continue
            # 其他队列消息按正常处理
            user_input = reminder_msg
        else:
            try:
                user_input = input_q.get(timeout=PROACTIVE_CHECK_INTERVAL)
            except queue.Empty:
                # 空闲时检查主动调度（同一条消息 10 分钟内不重复发）
                now_ts = time.time()
                context = {
                    "current_time": datetime.now().strftime("%H:%M"),
                    "idle_minutes": get_idle_minutes(),
                    "pending_reminders": get_pending_reminders(),
                }
                engage, content = should_proactively_engage(context)
                if engage and content:
                    # 去重：内容和上次一样且 10 分钟内发过 → 跳过
                    if content != _last_proactive_msg or (now_ts - _last_proactive_time) > 600:
                        _last_proactive_msg = content
                        _last_proactive_time = now_ts
                        print(f"\n小知(主动): {clean_text(content)}")
                        client.save_dialogue("assistant", content)
                continue

        if user_input is None or user_input.strip().lower() in ("exit", "quit"):
            break

        # 记录用户活跃
        record_user_activity()

        # 检查是否含时间意图 → 注册提醒
        reminder_time = extract_reminder_time(user_input)
        if reminder_time:
            register_reminder(user_input, reminder_time)

        try:
            client.save_dialogue("user", user_input)

            print("助手正在思考...")
            final = None
            for event in app.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config, stream_mode="values"
            ):
                final = event
            if final and final.get("messages"):
                last = final["messages"][-1]
                if getattr(last, "content", ""):
                    print(f"\n助手: {clean_text(last.content)}")
            print("\n你: ", end="", flush=True)
        except Exception as e:
            print(f"\n出错: {e}")
            print("\n你: ", end="", flush=True)

    client.close()


if __name__ == "__main__":
    main()
