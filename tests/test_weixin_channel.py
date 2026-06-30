"""测试 weixin/channel.py — 消息提取 / token 错误检测 / URL 构建。"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.weixin.channel import (
    extract_text, is_bot_message, check_token_error, is_rate_limited,
    _random_wechat_uin, _build_headers, _build_request_body,
)


class TestExtractText:
    """消息文本提取。"""

    def test_extract_normal_text(self):
        msg = {
            "item_list": [
                {"type": 1, "text_item": {"text": "你好"}},
            ]
        }
        assert extract_text(msg) == "你好"

    def test_extract_empty_items(self):
        assert extract_text({"item_list": []}) == ""

    def test_extract_no_item_list(self):
        assert extract_text({}) == ""

    def test_extract_mixed_items_skips_non_text(self):
        msg = {
            "item_list": [
                {"type": 2, "image_item": {}},
                {"type": 1, "text_item": {"text": "图片后面的话"}},
            ]
        }
        assert extract_text(msg) == "图片后面的话"

    def test_extract_multiple_text_items_concat(self):
        msg = {
            "item_list": [
                {"type": 1, "text_item": {"text": "第一句"}},
                {"type": 1, "text_item": {"text": "第二句"}},
            ]
        }
        assert extract_text(msg) == "第一句第二句"


class TestIsBotMessage:
    """BOT 回声过滤。"""

    def test_bot_message_type_2(self):
        assert is_bot_message({"message_type": 2}) is True

    def test_user_message_type_1(self):
        assert is_bot_message({"message_type": 1}) is False

    def test_no_message_type(self):
        assert is_bot_message({"from_user_id": "xxx"}) is False


class TestCheckTokenError:
    """Token 过期检测 — 需 ret != 0 且 errcode in (-14, -15)。"""

    def test_errcode_minus_14_with_ret_nonzero(self):
        assert check_token_error({"ret": -1, "errcode": -14}) is True

    def test_errcode_minus_15_with_ret_nonzero(self):
        assert check_token_error({"ret": -1, "errcode": -15}) is True

    def test_errcode_0(self):
        assert check_token_error({"ret": -1, "errcode": 0}) is False

    def test_ret_0_skips_errcode_check(self):
        """ret == 0 直接返回 False，不检查 errcode。"""
        assert check_token_error({"ret": 0, "errcode": -14}) is False

    def test_negative_errcode_not_14_15(self):
        assert check_token_error({"ret": -1, "errcode": -10}) is False


class TestIsRateLimited:
    """限流检测。"""

    def test_ret_minus_2(self):
        assert is_rate_limited({"ret": -2}) is True

    def test_ret_0(self):
        assert is_rate_limited({"ret": 0}) is False

    def test_no_ret(self):
        assert is_rate_limited({}) is False


class TestRandomWechatUin:
    """随机 UIN 生成。"""

    def test_returns_string(self):
        uin = _random_wechat_uin()
        assert isinstance(uin, str)

    def test_is_base64_like(self):
        uin = _random_wechat_uin()
        # base64 只含 A-Za-z0-9+/= 用于 padding
        import re
        assert re.match(r'^[A-Za-z0-9+/]+=*$', uin) is not None

    def test_different_each_call(self):
        uins = {_random_wechat_uin() for _ in range(10)}
        assert len(uins) > 1  # 概率极低的全相同


class TestBuildHeaders:
    """请求头构建 — AuthorizationType 固定，Bearer 仅在有 token 时添加。"""

    def test_with_token(self):
        headers = _build_headers("test_token_123")
        assert headers["Authorization"] == "Bearer test_token_123"
        assert headers["AuthorizationType"] == "ilink_bot_token"
        assert "X-WECHAT-UIN" in headers

    def test_without_token_no_auth_header(self):
        """无 token 时不添加 Authorization 头（登录接口）。"""
        headers = _build_headers(None)
        assert "Authorization" not in headers
        assert headers["AuthorizationType"] == "ilink_bot_token"
        assert "X-WECHAT-UIN" in headers


class TestBuildRequestBody:
    """请求体构建（手动 Content-Length）。"""

    def test_body_and_headers(self):
        body, headers = _build_request_body({"key": "value"})
        assert isinstance(body, bytes)
        assert body == b'{"key": "value"}'
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert headers["Content-Length"] == str(len(body))

    def test_cl_matches_body(self):
        body, headers = _build_request_body({"a": 1, "b": "测试"})
        assert int(headers["Content-Length"]) == len(body)

    def test_empty_payload(self):
        body, headers = _build_request_body({})
        assert body == b"{}"
        assert headers["Content-Length"] == "2"
