"""微信 Bot 接入模块 -- 基于 iLink 协议的微信消息收发通道。

模块结构:
  channel.py  — 协议层：7 个 HTTP API 封装 + Content-Length 手动计算
  auth.py     — 认证层：扫码登录（GET）+ 凭证持久化
  bot.py      — 主循环：并发消息处理 + Agent 调用（astream）+ 回复发送

对外导出:
  WeixinBot   — Bot 主类（bot.py）
  fetch_qrcode / poll_qrcode_status  — 登录相关（channel.py）
  get_updates / send_message / ...    — 业务 API（channel.py）
  login / load_credentials / save_credentials — 认证（auth.py）
"""

from src.weixin.bot import WeixinBot
from src.weixin.channel import (
    fetch_qrcode,
    poll_qrcode_status,
    get_updates,
    send_message,
    send_typing,
    get_config,
    get_upload_url,
)
from src.weixin.auth import login, load_credentials, save_credentials, LoginCredentials

__all__ = [
    "WeixinBot",
    "fetch_qrcode",
    "poll_qrcode_status",
    "get_updates",
    "send_message",
    "send_typing",
    "get_config",
    "get_upload_url",
    "login",
    "load_credentials",
    "save_credentials",
    "LoginCredentials",
]
