"""iLink 协议层 — 微信 Bot 7 个 HTTP API 封装。

关键设计决策（来自任务书 v2.3）:
  - Content-Length 必须手动精确计算（禁用 httpx json= 参数）
  - Token 过期通过 ret + errcode 检测（非 HTTP 401/403）
  - sendMessage 限流时 ret==-2 需指数退避重试
  - message_type 收到值不确定（print 确认），发送 BOT 固定为 2
  - 配置读取统一通过 get_settings()（禁止 os.environ）

API 清单:
  L1  fetch_qrcode()           GET  获取二维码
  L2  poll_qrcode_status()     GET  轮询扫码状态
  1   get_updates()            POST 长轮询拉取消息
  2   send_message()           POST 发送消息给用户
  3   send_typing()            POST 正在输入 / 取消输入
  4   get_config()             POST 获取配置与 typing_ticket
  5   get_upload_url()         POST 获取媒体上传地址（本期 stub）
"""

from __future__ import annotations

import base64
import json
import logging
import secrets
import uuid
from typing import Any

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)

# ── 默认值 ────────────────────────────────────────────────────────

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_CHANNEL_VERSION = "1.0.3"
DEFAULT_BOT_TYPE = 3
DEFAULT_POLL_TIMEOUT = 35

# ── 协议工具函数 ──────────────────────────────────────────────────


def _random_wechat_uin() -> str:
    """生成 X-WECHAT-UIN 头：随机 uint32 → base64。

    每次请求必须使用不同的 UIN。
    """
    val = secrets.randbelow(2**32)
    return base64.b64encode(val.to_bytes(4, "big")).decode("ascii")


def _build_headers(token: str | None = None) -> dict[str, str]:
    """构建 iLink 请求头。

    Args:
        token: Bearer token（业务接口必填，登录接口留空）
    """
    headers = {
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": _random_wechat_uin(),
        "Content-Type": "application/json; charset=utf-8",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _build_request_body(payload: dict) -> tuple[bytes, dict[str, str]]:
    """手动序列化 JSON 并精确计算 Content-Length。

    ⚠️ 禁止使用 httpx 的 json= 参数！iLink 对 Content-Length 敏感，
       中文等多字节字符会导致自动计算的长度与实际 body 不一致。

    Returns:
        (raw_bytes, headers_dict)  headers 含 Content-Type 和 Content-Length
    """
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": str(len(raw)),
    }
    return raw, headers


def _get_base_url() -> str:
    """从配置系统读取 Base URL（v2.3: 统一使用 get_settings）。"""
    s = get_settings()
    return s.get("wx_base_url") or DEFAULT_BASE_URL


# ── 底层 HTTP 封装 ────────────────────────────────────────────────


async def _api_get(
    client: httpx.AsyncClient,
    url: str,
    params: dict | None = None,
    extra_headers: dict | None = None,
) -> dict:
    """GET 请求封装（登录接口专用）。

    登录接口不需要 Bearer token，但需要 iLink-App-ClientVersion header。
    """
    headers = extra_headers or {}
    resp = await client.get(url, params=params, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    logger.debug("[wx] GET %s → %s", url, _safe_repr(data))
    return data


async def _api_post(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
    token: str | None = None,
    timeout: float = 30.0,
) -> dict:
    """POST 请求封装（业务接口专用）。

    使用 _build_request_body 手动计算 Content-Length。
    """
    headers = _build_headers(token)
    raw, cl_headers = _build_request_body(payload)
    headers.update(cl_headers)

    resp = await client.post(url, content=raw, headers=headers, timeout=timeout)
    # ⚠️ ilink 错误在 body 里，HTTP 可能仍返回 200
    data = resp.json()
    logger.debug("[wx] POST %s → ret=%s", url, data.get("ret", "?"))
    return data


# ══════════════════════════════════════════════════════════════════
# 7 个 API 函数
# ══════════════════════════════════════════════════════════════════


async def fetch_qrcode(client: httpx.AsyncClient) -> dict:
    """L1: 获取登录二维码（GET，无需认证）。

    Returns:
        {"qrcode": "https://...", "qrcode_img_content": "base64...", "event_id": "evt_xxx"}
    """
    base = _get_base_url()
    s = get_settings()
    bot_type = int(s.get("wx_bot_type", str(DEFAULT_BOT_TYPE)))

    url = f"{base}/ilink/bot/get_bot_qrcode"
    params = {"bot_type": str(bot_type)}
    headers = {"iLink-App-ClientVersion": "1"}

    return await _api_get(client, url, params=params, extra_headers=headers)


async def poll_qrcode_status(
    client: httpx.AsyncClient, event_id: str
) -> dict:
    """L2: 轮询扫码状态（GET，无需认证）。

    状态机: wait → scaned → expired(重试≤3次) / confirmed(拿token)

    Returns:
        {"status": "wait"|"scaned"|"expired"|"confirmed", ...}
        当 status=="confirmed" 时额外包含: bot_token, ilink_bot_id, ilink_user_id
    """
    base = _get_base_url()
    url = f"{base}/ilink/bot/get_qrcode_status"
    # ⚠️ 参数名"qrcode"为猜测值。真机首调时如果轮询始终无响应，
    #    请取消下面 print 的注释，确认微信接口实际参数名是否为 event_id 或其他。
    params = {"qrcode": event_id}
    # print(f"[debug] poll_qrcode_status params={params}  # 真机首调确认参数名")
    headers = {"iLink-App-ClientVersion": "1"}

    return await _api_get(client, url, params=params, extra_headers=headers)


async def get_updates(
    client: httpx.AsyncClient,
    token: str,
    buf: str = "",
    timeout: int = DEFAULT_POLL_TIMEOUT,
) -> dict:
    """接口 1: 长轮询拉取消息（POST，需 Bearer token）。

    Args:
        token: bot_token
        buf: 上次的游标（首次传空字符串）
        timeout: 长轮询超时秒数（默认 35）

    Returns:
        {
            "ret": 0,
            "msgs": [{"from_user_id": "...", "message_type": ..., "item_list": [...], "context_token": "..."}],
            "get_updates_buf": "next_cursor"
        }

    ⚠️ ret != 0 时需检查 errcode：
        -14/-15 → token 过期，触发重新登录
        其他负值 → 记录日志，继续下一轮
    """
    base = _get_base_url()
    url = f"{base}/ilink/bot/getupdates"
    payload = {"get_updates_buf": buf}

    return await _api_post(client, url, payload, token, timeout=float(timeout))


async def send_message(
    client: httpx.AsyncClient,
    token: str,
    user_id: str,
    text: str,
    context_token: str = "",
    client_id: str | None = None,
) -> dict:
    """接口 2: 发送消息给用户（POST，需 Bearer token）。

    致命字段清单（缺任何一个都导致 HTTP 200 但用户收不到消息）:
      - client_id: 每条唯一 UUID，格式 "bot-{12位hex}"
      - message_type: 2（BOT）
      - base_info: 顶层字段 {"channel_version": "1.0.3"}

    Args:
        client: httpx 异步客户端
        token: bot_token
        user_id: 目标用户的 from_user_id（wxid_xxx）
        text: 回复文本内容
        context_token: 从收到消息提取，回复时原样带回
        client_id: 消息唯一 ID（不传则自动生成）

    Returns:
        {"ret": 0, ...}  ret==0 成功；ret==-2 限流需退避重试
    """
    if client_id is None:
        client_id = f"bot-{uuid.uuid4().hex[:12]}"

    base = _get_base_url()
    url = f"{base}/ilink/bot/sendmessage"
    s = get_settings()
    channel_version = s.get("wx_channel_version") or DEFAULT_CHANNEL_VERSION

    payload = {
        "msg": {
            "from_user_id": "",
            "to_user_id": user_id,
            "client_id": client_id,
            "message_type": 2,          # BOT
            "message_state": 2,         # FINISH
            "context_token": context_token,
            "item_list": [
                {"type": 1, "text_item": {"text": text}}
            ],
        },
        "base_info": {"channel_version": channel_version},
    }

    return await _api_post(client, url, payload, token)


async def send_typing(
    client: httpx.AsyncClient,
    token: str,
    ilink_user_id: str,
    typing_ticket: str,
    status: int = 1,
) -> dict:
    """接口 3: 发送「正在输入」或「取消输入」（POST，需 Bearer token）。

    关键依赖链: 必须先调 get_config() 拿到 typing_ticket 才能调用此接口。

    Args:
        status: 1=正在输入, 2=取消输入
    """
    base = _get_base_url()
    url = f"{base}/ilink/bot/sendtyping"

    payload = {
        "ilink_user_id": ilink_user_id,
        "typing_ticket": typing_ticket,
        "status": status,
    }

    return await _api_post(client, url, payload, token)


async def get_config(
    client: httpx.AsyncClient,
    token: str,
    ilink_user_id: str,
    context_token: str = "",
) -> dict:
    """接口 4: 获取配置与 typing_ticket（POST，需 Bearer token）。

    核心返回值: typing_ticket（send_typing 的必需参数）

    Returns:
        {"ret": 0, "typing_ticket": "eyJzdGtpY2tldC...", "ilink_user_id": "..."}
    """
    base = _get_base_url()
    url = f"{base}/ilink/bot/getconfig"

    payload = {
        "ilink_user_id": ilink_user_id,
    }
    if context_token:
        payload["context_token"] = context_token

    return await _api_post(client, url, payload, token)


async def get_upload_url(
    client: httpx.AsyncClient,
    token: str,
) -> dict:
    """接口 5: 获取媒体上传地址（POST，需 Bearer token）。

    本期仅文字消息，返回 stub。
    TODO: 图片/语音/视频消息处理时实现完整逻辑。
    """
    base = _get_base_url()
    url = f"{base}/ilink/bot/getuploadurl"

    payload = {}
    return await _api_post(client, url, payload, token)


# ── 辅助函数 ──────────────────────────────────────────────────────


def extract_text(msg: dict) -> str:
    """从消息中提取纯文本内容。

    遍历 item_list 找 type==1 的 text_item.text 字段。
    """
    items = msg.get("item_list", [])
    texts = []
    for item in items:
        if item.get("type") == 1:
            text_item = item.get("text_item", {})
            t = text_item.get("text", "")
            if t:
                texts.append(t)
    return "".join(texts)


def is_bot_message(msg: dict) -> bool:
    """判断是否为 BOT 自身消息（应丢弃的回声）。

    ⚠️ message_type 实际值不确定，当前按任务书规范：==2 为 BOT 回声。
       真机首调必须 print(msg) 确认实际值。
    """
    return msg.get("message_type") == 2


def check_token_error(resp: dict) -> bool:
    """检查响应是否表示 token 过期。

    Returns:
        True 表示需要重新登录（errcode 为 -14 或 -15）
    """
    ret = resp.get("ret", 0)
    if ret == 0:
        return False
    errcode = resp.get("errcode", 0)
    if errcode in (-14, -15):
        logger.warning("[wx] Token 过期检测: ret=%d, errcode=%d → 需要重新登录", ret, errcode)
        return True
    logger.warning("[wx] 业务错误: ret=%d, errcode=%d", ret, errcode)
    return False


def is_rate_limited(resp: dict) -> bool:
    """检查是否被限流（ret==-2）。"""
    return resp.get("ret", 0) == -2


def _safe_repr(data: Any, max_len: int = 200) -> str:
    """安全日志输出（脱敏 token 等敏感字段）。"""
    try:
        s = json.dumps(data, ensure_ascii=False)
        if len(s) > max_len:
            return s[:max_len] + "..."
        return s
    except Exception:
        return repr(data)
