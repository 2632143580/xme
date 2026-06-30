"""微信 Bot 用户隔离层 — 通过 contextvars 传递当前 wx_user_id。

设计（任务书路径 B）：
  - bot.py._call_agent() 调用前设置当前 user_id
  - note_tools / graph_tools / client 读取上下文
  - 无上下文时（CLI / API 模式）降级为默认值 "user1"

使用:
    from src.weixin.user_context import current_user_id, set_current_user
    token = set_current_user("wx_openid_xxx")
    try:
        # 所有工具调用自动读取此 user_id
        ...
    finally:
        current_user_id.reset(token)
"""

import contextvars

# ContextVar 默认值 "user1" 确保 CLI/API 模式向后兼容
current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "wx_user_id", default="user1"
)


def get_current_user() -> str:
    """返回当前请求对应的用户 ID（微信模式为 wx_user_id，CLI/API 为 "user1"）。"""
    return current_user_id.get()


def set_current_user(user_id: str) -> contextvars.Token:
    """设置当前上下文用户 ID，返回 Token 供后续 reset。"""
    return current_user_id.set(user_id)
