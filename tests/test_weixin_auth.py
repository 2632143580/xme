"""测试 weixin/auth.py — 凭证持久化 / 加载 / 清除。"""
import os
import sys
import json
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.weixin.auth import (
    LoginCredentials, save_credentials, load_credentials, clear_credentials,
    CREDENTIALS_DIR, CREDENTIALS_FILE,
)


class TestLoginCredentials:
    """凭证数据类。"""

    def test_from_valid_dict(self):
        d = {
            "token": "tok_abc",
            "base_url": "https://ilinkai.weixin.qq.com",
            "ilink_bot_id": "bot_1",
            "ilink_user_id": "user_1",
            "login_time": "2026-06-28T10:00:00Z",
        }
        c = LoginCredentials.from_dict(d)
        assert c.token == "tok_abc"
        assert c.base_url == "https://ilinkai.weixin.qq.com"
        assert c.is_valid is True

    def test_is_valid_false_when_missing_token(self):
        c = LoginCredentials(
            token="", base_url="http://x", ilink_bot_id="",
            ilink_user_id="user_1", login_time=""
        )
        assert c.is_valid is False

    def test_is_valid_false_when_missing_ilink_user_id(self):
        c = LoginCredentials(
            token="tok", base_url="http://x", ilink_bot_id="",
            ilink_user_id="", login_time=""
        )
        assert c.is_valid is False

    def test_to_dict_roundtrip(self):
        original = LoginCredentials(
            token="tok", base_url="http://x", ilink_bot_id="b1",
            ilink_user_id="u1", login_time="2026-06-28T10:00:00Z"
        )
        restored = LoginCredentials.from_dict(original.to_dict())
        assert restored.token == original.token
        assert restored.ilink_user_id == original.ilink_user_id
        assert restored.is_valid


class TestCredentialsPersistence:
    """凭证文件持久化。"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self, monkeypatch, tmp_path):
        """替换凭证文件路径到临时目录。"""
        creds_file = tmp_path / "wx_credentials.json"
        creds_dir = str(tmp_path)
        monkeypatch.setattr("src.weixin.auth.CREDENTIALS_DIR", creds_dir)
        monkeypatch.setattr("src.weixin.auth.CREDENTIALS_FILE", str(creds_file))
        yield
        # 清理
        if creds_file.exists():
            creds_file.unlink()

    def test_save_and_load(self):
        c = LoginCredentials(
            token="tok", base_url="http://x", ilink_bot_id="b1",
            ilink_user_id="u1", login_time="2026-06-28T10:00:00Z"
        )
        save_credentials(c)
        loaded = load_credentials()
        assert loaded is not None
        assert loaded.token == "tok"
        assert loaded.ilink_user_id == "u1"

    def test_load_nonexistent(self):
        clear_credentials()
        assert load_credentials() is None

    def test_clear(self):
        c = LoginCredentials(
            token="tok", base_url="http://x", ilink_bot_id="b1",
            ilink_user_id="u1", login_time=""
        )
        save_credentials(c)
        clear_credentials()
        assert load_credentials() is None

    def test_load_corrupted_file(self, tmp_path):
        """测试损坏的 JSON 返回 None。"""
        assert CREDENTIALS_FILE != ""
        with open(CREDENTIALS_FILE, "w") as f:
            f.write("{not json")
        assert load_credentials() is None
