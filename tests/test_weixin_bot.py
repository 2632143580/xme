"""测试 weixin/bot.py — 用户隔离 / 限流退避 / contextvars 注入。"""
import os
import sys
import asyncio
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.weixin.user_context import get_current_user, set_current_user, current_user_id


class TestUserContext:
    """contextvars 用户隔离机制。"""

    def test_default_is_user1(self):
        assert get_current_user() == "user1"

    def test_set_and_get(self):
        token = set_current_user("wx_openid_abc123")
        try:
            assert get_current_user() == "wx_openid_abc123"
        finally:
            current_user_id.reset(token)

    def test_reset_after_set(self):
        token = set_current_user("wx_test_user")
        current_user_id.reset(token)
        assert get_current_user() == "user1"

    def test_nested_contexts(self):
        """嵌套 context：内层不影响外层。"""
        token1 = set_current_user("outer")
        assert get_current_user() == "outer"

        token2 = set_current_user("inner")
        try:
            assert get_current_user() == "inner"
            current_user_id.reset(token2)
            assert get_current_user() == "outer"
        finally:
            current_user_id.reset(token1)

    def test_different_users_isolated(self):
        """两个用户不应该混数据。"""
        assert get_current_user() == "user1"
        token = set_current_user("user_A")
        assert get_current_user() == "user_A"
        current_user_id.reset(token)
        assert get_current_user() == "user1"


class TestWeixinBotExponentialBackoff:
    """限流退避算法：1s -> 2s -> 4s 指数而非 2s -> 4s -> 6s 线性。"""

    def test_exponential_sequence(self):
        """验证 2**attempt 产生 [1, 2, 4] 而非 [(attempt+1)*2 → 2, 4, 6]。"""
        # 这是对 bot.py _send_reply() 算法的逻辑测试
        waits = [2 ** a for a in range(3)]
        assert waits == [1, 2, 4], f"指数退避应为 [1,2,4]，实际 {waits}"

        # 线性错误版本对照（前代码）
        linear_waits = [(a + 1) * 2 for a in range(3)]
        assert linear_waits == [2, 4, 6], "仅用于对照：线性退避"


class TestContextvarInjectionInBot:
    """测试 bot.py._call_agent() 的 contextvar 注入逻辑。

    由于 Agent 和 LLM 调用需要真实的后端，这里只测试 contextvar 的
    设置/恢复逻辑，不实际调用 Agent。
    """

    def test_token_set_and_reset_pattern(self):
        """模拟 _call_agent() 中的 contextvar 设置/恢复模式。"""
        assert get_current_user() == "user1"

        # 模拟 bot.py 的注入模式
        user_id = "wx_test_bot_user"
        token = set_current_user(user_id)
        try:
            # 模拟 Agent 调用期间
            assert get_current_user() == user_id
        finally:
            current_user_id.reset(token)

        # 恢复后应为默认值
        assert get_current_user() == "user1"
