"""认证层 — 微信扫码登录 + 凭证管理。

登录流程（GET 接口，无 Bearer 认证）:
  1. fetch_qrcode()  → 获取二维码 URL + event_id
  2. 终端渲染二维码（qrcode 库或浏览器打开 URL）
  3. poll_qrcode_status(event_id)  → 轮询直到 confirmed
  4. 拿到 bot_token + ilink_bot_id + ilink_user_id
  5. 凭证持久化到 data/wx_credentials.json

凭证文件格式 (JSON):
  {
    "token": "eyJhbGci...",
    "baseUrl": "https://ilinkai.weixin.qq.com",
    "ilink_bot_id": "bot_xxx@im.wechat",
    "ilink_user_id": "user_xxx@im.wechat",
    "login_time": "2026-01-01T12:00:00"
  }

⚠️ v2.3 注意:
  - 凭证是 JSON 格式（非 key=value），不适合 write_env()，直接文件操作
  - 其他 WX_ 配置项应通过 get_settings() 读取
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)

# ── 凭证文件路径 ──────────────────────────────────────────────────

CREDENTIALS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
CREDENTIALS_FILE = os.path.join(CREDENTIALS_DIR, "wx_credentials.json")

# 轮询参数
POLL_INTERVAL = 3       # 秒
MAX_POLL_ATTEMPTS = 60   # 最长等待约 3 分钟（60 × 3s）
QR_EXPIRED_MAX_RETRIES = 3  # 二维码过期最多重试次数


@dataclass
class LoginCredentials:
    """登录凭证数据类。"""

    token: str
    base_url: str
    ilink_bot_id: str
    ilink_user_id: str
    login_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "baseUrl": self.base_url,
            "ilink_bot_id": self.ilink_bot_id,
            "ilink_user_id": self.ilink_user_id,
            "login_time": self.login_time,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LoginCredentials":
        return cls(
            token=d["token"],
            base_url=d.get("baseUrl", d.get("base_url", "")),
            ilink_bot_id=d["ilink_bot_id"],
            ilink_user_id=d["ilink_user_id"],
            login_time=d.get("login_time", ""),
        )

    @property
    def is_valid(self) -> bool:
        """基本有效性检查（有 token 即认为可用，过期由 errcode 检测）。"""
        return bool(self.token and self.ilink_user_id)


# ── 凭证持久化 ────────────────────────────────────────────────────


def save_credentials(credentials: LoginCredentials) -> str:
    """保存凭证到 JSON 文件。

    Returns:
        保存的文件路径
    """
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(credentials.to_dict(), f, ensure_ascii=False, indent=2)
    logger.info("[wx-auth] 凭证已保存: %s", CREDENTIALS_FILE)
    return CREDENTIALS_FILE


def load_credentials() -> LoginCredentials | None:
    """加载已保存的凭证。

    Returns:
        LoginCredentials 对象，文件不存在或无效时返回 None
    """
    if not os.path.exists(CREDENTIALS_FILE):
        return None
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        creds = LoginCredentials.from_dict(data)
        if creds.is_valid:
            logger.info("[wx-auth] 已加载凭证 (user=%s)", creds.ilink_user_id)
            return creds
        else:
            logger.warning("[wx-auth] 凭证无效，将重新登录")
            return None
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("[wx-auth] 凭证文件损坏: %s", e)
        return None


def clear_credentials() -> None:
    """删除凭证文件（用于强制重新登录）。"""
    if os.path.exists(CREDENTIALS_FILE):
        os.remove(CREDENTIALS_FILE)
        logger.info("[wx-auth] 凭证已清除")


# ── 二维码渲染 ────────────────────────────────────────────────────


def render_qrcode_terminal(qr_url: str | None, qr_img_b64: str | None = None) -> None:
    """在终端渲染二维码。

    优先尝试 qrcode 库渲染图片内容；
    如果没有图片数据，打印 URL 让用户浏览器打开。
    """
    if qr_img_b64:
        try:
            import io
            import base64 as b64

            from PIL import Image

            img_data = b64.b64decode(qr_img_b64)
            img = Image.open(io.BytesIO(img_data))
            try:
                import qrcode as qr_lib

                if not qr_url:
                    print("[login] 二维码URL为空，无法渲染终端二维码")
                    return
                qr = qr_lib.main(qr_url)  # type: ignore
                return
            except ImportError:
                pass
            # fallback: 打印提示
            print("\n[wx] 请扫描以下二维码（或打开上方链接）:\n")
            # 尝试用终端显示
            try:
                from term_image.image import from_color as TermImage  # type: ignore

                TermImage(img).draw()
                return
            except ImportError:
                pass
        except Exception:
            pass

    if qr_url:
        print(f"\n[wx] 请在浏览器打开以下链接查看二维码:\n  {qr_url}\n")
        print("[wx] 或用手机扫一扫上面的二维码\n")
    else:
        print("[wx] 无法获取二维码图像")


# ── 登录流程 ──────────────────────────────────────────────────────


async def login(
    client: httpx.AsyncClient,
    force_relogin: bool = False,
    on_qrcode=None,
) -> LoginCredentials:
    """执行完整的扫码登录流程。

    Args:
        client: httpx 异步客户端
        force_relogin: 是否强制重新登录（忽略已有凭证）
        on_qrcode: 可选回调函数(qr_data: dict)，用于自定义二维码展示

    Returns:
        LoginCredentials 登录成功后的凭证

    Raises:
        RuntimeError: 登录失败（超时/过期/取消等）
    """
    # 1. 检查已有凭证
    if not force_relogin:
        existing = load_credentials()
        if existing and existing.is_valid:
            print(f"[wx] 复用已有凭证 (user={existing.ilink_user_id})")
            return existing

    # 2. 获取二维码
    from src.weixin.channel import fetch_qrcode, poll_qrcode_status

    expired_count = 0

    while expired_count < QR_EXPIRED_MAX_RETRIES:
        print("[wx] 正在获取登录二维码...")
        qr_data = await fetch_qrcode(client)

        event_id = qr_data.get("event_id", "")
        qr_url = qr_data.get("qrcode", "")
        qr_img = qr_data.get("qrcode_img_content", "")

        if not event_id:
            raise RuntimeError("[wx] 获取二维码失败: 缺少 event_id")

        # 展示二维码
        if on_qrcode:
            on_qrcode(qr_data)
        else:
            render_qrcode_terminal(qr_url, qr_img)

        print("[wx] 请在手机上确认授权（等待扫码）...")

        # 3. 轮询扫码状态
        for attempt in range(MAX_POLL_ATTEMPTS):
            await asyncio_sleep(POLL_INTERVAL)

            status_data = await poll_qrcode_status(client, event_id)
            status = status_data.get("status", "")

            if status == "confirmed":
                # ✅ 登录成功
                token = status_data.get("bot_token", "")
                bot_id = status_data.get("ilink_bot_id", "")
                user_id = status_data.get("ilink_user_id", "")

                if not token:
                    raise RuntimeError("[wx] 登录确认但未拿到 token")

                s = get_settings()
                base_url = s.get("wx_base_url") or "https://ilinkai.weixin.qq.com"

                creds = LoginCredentials(
                    token=token,
                    base_url=base_url,
                    ilink_bot_id=bot_id,
                    ilink_user_id=user_id,
                )
                save_credentials(creds)
                print(f"[wx] ✓ 登录成功! (user={user_id})")
                return creds

            elif status == "scaned":
                print("[wx] 已扫码，请在手机上确认...")

            elif status == "expired":
                print(f"[wx] 二维码已过期 ({expired_count + 1}/{QR_EXPIRED_MAX_RETRIES})")
                expired_count += 1
                break  # 外层循环会重新获取二维码

            elif status == "wait":
                # 继续等待
                if attempt % 10 == 0:  # 每 30 秒提示一次
                    print(f"[wx] 等待扫码中... ({attempt * POLL_INTERVAL}s)")
            else:
                logger.debug("[wx] 未知状态: %s", status)

        # 二维码过期，重试
        if status == "expired" and expired_count < QR_EXPIRED_MAX_RETRIES:
            print("[wx] 正在重新获取二维码...")
            continue

    raise RuntimeError(f"[wx] 登录失败: 二维码过期重试 {QR_EXPIRED_MAX_RETRIES} 次均未成功")


# ── 兼容层 ────────────────────────────────────────────────────────

async def asyncio_sleep(seconds: float) -> None:
    """异步 sleep（在 async 上下文中使用）。"""
    import asyncio
    await asyncio.sleep(seconds)
