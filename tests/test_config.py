"""测试 config 模块。"""
import os
import pytest


def test_get_settings_returns_dict():
    from src.config import get_settings
    s = get_settings()
    assert isinstance(s, dict)


def test_get_settings_has_expected_keys():
    from src.config import get_settings
    s = get_settings()
    expected_keys = [
        "llm_provider",
        "volcengine_api_key",
        "volcengine_base_url",
        "volcengine_model",
    ]
    for key in expected_keys:
        assert key in s, f"Missing key: {key}"


def test_llm_factory_get_llm():
    from src.llm_factory import get_llm
    # 这会尝试创建真实的 LLM 客户端，需要有效的 API key
    # 在 CI 环境中应该 mock 掉
    try:
        llm = get_llm()
        assert llm is not None
    except Exception as e:
        pytest.skip(f"LLM 创建失败（可能是 API Key 无效）: {e}")
