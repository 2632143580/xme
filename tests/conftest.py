"""公共 fixture —— env, mock LLM, 临时 DB。"""
import os
import sqlite3
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """自动设测试用 env var，测试结束后恢复。"""
    monkeypatch.setenv("LLM_PROVIDER", "volcengine")
    monkeypatch.setenv("VOLCENGINE_API_KEY", "test-key")
    monkeypatch.setenv(
        "VOLCENGINE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
    )
    monkeypatch.setenv("VOLCENGINE_MODEL", "doubao-seed-2-0-lite-260215")
    monkeypatch.setenv("SQLITE_PATH", ":memory:")


@pytest.fixture
def mock_llm():
    """mock LLM，返回固定回复。"""
    mock = MagicMock()
    mock.invoke.return_value = MagicMock(
        content="OK",
        tool_calls=[],
    )
    mock.bind_tools.return_value = mock
    return mock


@pytest.fixture
def tmp_db(tmp_path):
    """临时 SQLite DB，测试结束后自动清理。"""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );
    CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        segment_text TEXT NOT NULL,
        summary TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );
    """)
    conn.commit()
    yield conn
    conn.close()
