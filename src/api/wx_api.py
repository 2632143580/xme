"""微信 Bot REST API — 供前端控制台调用。"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException

from src.config import get_settings
from src.weixin.channel import fetch_qrcode, poll_qrcode_status
from src.weixin.auth import load_credentials, LoginCredentials

router = APIRouter(prefix="/api/weixin", tags=["weixin"])

# ── 状态文件路径 ────────────────────────────────────────────────

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data")
WX_STATE_FILE = os.path.join(DATA_DIR, "wx_bot_state.json")
WX_MESSAGES_FILE = os.path.join(DATA_DIR, "wx_messages.json")


def _read_state() -> dict:
    """读取 Bot 运行状态。"""
    try:
        with open(WX_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"status": "stopped", "uptime": 0, "bot_id": "", "user_id": ""}


def _read_messages(limit: int = 50) -> list[dict]:
    """读取最近的微信消息记录。"""
    try:
        with open(WX_MESSAGES_FILE, "r", encoding="utf-8") as f:
            msgs = json.load(f)
        # 最新在前
        return sorted(msgs, key=lambda m: m.get("timestamp", 0), reverse=True)[:limit]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


# ══════════════════════════════════════════════════════════════════
# 登录相关
# ══════════════════════════════════════════════════════════════════


@router.post("/login")
async def start_login():
    """获取登录二维码。返回 event_id 和 qrcode。"""
    try:
        async with httpx.AsyncClient() as client:
            data = await fetch_qrcode(client)
        qrcode_img = data.get("qrcode_img_content", "")
        return {
            "event_id": data.get("event_id", ""),
            "qrcode": qrcode_img,  # 前端期望 qrcode 字段
        }
    except Exception as e:
        raise HTTPException(500, f"获取二维码失败: {e}")


@router.get("/login-status")
async def get_login_status(event_id: str):
    """轮询扫码状态：映射为前端期望的 state 字段。"""
    try:
        async with httpx.AsyncClient() as client:
            data = await poll_qrcode_status(client, event_id)
        status = data.get("status", "wait")

        # 映射为前端期望的状态值
        state_map = {
            "wait": "awaiting_scan",
            "scaned": "awaiting_scan",
            "confirmed": "logged_in",
            "expired": "expired",
        }
        state = state_map.get(status, "error")

        result = {"state": state}

        if state == "logged_in":
            # 保存凭证
            creds = LoginCredentials(
                bot_token=data.get("bot_token", ""),
                ilink_bot_id=data.get("ilink_bot_id", ""),
                ilink_user_id=data.get("ilink_user_id", ""),
            )
            from src.weixin.auth import save_credentials
            save_credentials(creds)
        return result
    except Exception as e:
        raise HTTPException(500, f"查询状态失败: {e}")


# ══════════════════════════════════════════════════════════════════
# 状态与消息
# ══════════════════════════════════════════════════════════════════


@router.get("/status")
async def bot_status():
    """获取 Bot 运行状态，返回前端期望的 WxStatus 格式。"""
    state = _read_state()
    creds = load_credentials()

    # 推导 WxState
    has_cred = creds is not None and bool(creds.bot_token)
    is_running = state.get("status") == "running"
    has_error = bool(state.get("last_error", ""))

    if not has_cred:
        wx_state = "logged_out"
    elif is_running:
        wx_state = "logged_in"
    elif has_error:
        wx_state = "error"
    else:
        wx_state = "logged_out"

    result = {"state": wx_state}

    if has_cred:
        result["nickname"] = creds.ilink_user_id or ""
        result["wxid"] = creds.ilink_bot_id or ""

    return result


@router.get("/messages")
async def bot_messages(limit: int = 50):
    """获取最近的微信消息记录。"""
    return {"messages": _read_messages(limit)}


# ══════════════════════════════════════════════════════════════════
# 测试发消息
# ══════════════════════════════════════════════════════════════════


@router.post("/send")
async def test_send_message(body: dict):
    """向微信用户发送测试消息（需已登录）。"""
    to = body.get("to", "")
    content = body.get("content", "")
    if not to or not content:
        raise HTTPException(400, "to 和 content 必填")

    creds = load_credentials()
    if not creds or not creds.bot_token:
        raise HTTPException(400, "未登录，请先扫码登录")

    try:
        async with httpx.AsyncClient() as client:
            from src.weixin.channel import send_message
            result = await send_message(client, creds.bot_token, to, content)
        ret = result.get("ret", -999)
        if ret != 0:
            raise HTTPException(500, f"发送失败: ret={ret}, errcode={result.get('errcode','?')}")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"发送异常: {e}")
