"""LLM Provider Factory — 可扩展的模型切换层。

设计原则：
- 每个 provider 在 .env 中独占一组前缀变量（API_KEY / BASE_URL / MODEL）
- LLM_PROVIDER 一行切换
- 新增 provider：改 .env + 在 PROVIDER_CONFIGS 加一条 entry
- 非 OpenAI 兼容的 provider：在 get_llm() 中按 provider 返回不同客户端
"""

import os
import warnings
from langchain_openai import ChatOpenAI

from src.config import get_settings

# ── Provider 注册表 ──────────────────────────────────────────────
# key = provider 名, value = {api_key, base_url, model} 在 settings 中的 key
PROVIDER_CONFIGS = {
    "volcengine": {
        "api_key_key": "volcengine_api_key",
        "base_url_key": "volcengine_base_url",
        "model_key": "volcengine_model",
    },
    "deepseek": {
        "api_key_key": "deepseek_api_key",
        "base_url_key": "deepseek_base_url",
        "model_key": "deepseek_model",
    },
    "openai": {
        "api_key_key": "openai_api_key",
        "base_url_key": "openai_base_url",
        "model_key": "openai_model",
    },
}

# ── 向后兼容 fallback ──────────────────────────────────────────
_LEGACY_API_KEY = "openai_api_key"
_LEGACY_BASE_URL = "openai_base_url"
_LEGACY_MODEL = "openai_model"


def get_llm(provider: str | None = None, model: str | None = None, **kwargs):
    """创建 LLM 客户端。

    Args:
        provider: 不传则读 LLM_PROVIDER 环境变量，再 fallback 到旧格式
        model:   覆盖 provider 默认模型
        **kwargs: 透传给 ChatOpenAI（temperature, timeout 等）

    Returns:
        ChatOpenAI 实例（或未来其他 LangChain 客户端）

    Raises:
        ValueError: provider 未知或必要配置缺失
    """
    s = get_settings()
    provider = provider or s.get("llm_provider", "")

    # ── 向后兼容：无 LLM_PROVIDER 时走旧格式 ──
    if not provider:
        warnings.warn(
            "LLM_PROVIDER 未设置，使用旧格式 OPENAI_API_KEY/OPENAI_BASE_URL/MODEL_NAME。"
            "建议迁移到多 provider 格式。",
            DeprecationWarning,
        )
        api_key = s.get(_LEGACY_API_KEY, "")
        base_url = s.get(_LEGACY_BASE_URL, "")
        model_name = model or s.get(_LEGACY_MODEL, "gpt-3.5-turbo")
        return _build_chat_openai(api_key, base_url, model_name, **kwargs)

    # ── 新格式：按 provider 查找 ──
    config = PROVIDER_CONFIGS.get(provider)
    if not config:
        raise ValueError(
            f"未知 provider: '{provider}'。可用: {list(PROVIDER_CONFIGS.keys())}"
        )

    api_key = s.get(config["api_key_key"], "")
    base_url = s.get(config["base_url_key"], "")
    model_name = model or s.get(config["model_key"], "")

    if not api_key:
        raise ValueError(
            f"缺少 {config['api_key_key']}，请在 .env 中设置或切换 LLM_PROVIDER"
        )
    if not base_url:
        raise ValueError(
            f"缺少 {config['base_url_key']}，请在 .env 中设置或切换 LLM_PROVIDER"
        )
    if not model_name:
        raise ValueError(
            f"缺少 {config['model_key']}，请在 .env 中设置或切换 LLM_PROVIDER"
        )

    return _build_chat_openai(api_key, base_url, model_name, **kwargs)


def _build_chat_openai(api_key: str, base_url: str, model: str, **kwargs):
    """构造 ChatOpenAI 实例，统一默认值。"""
    defaults = {"temperature": 0.7, "timeout": 30}
    defaults.update(kwargs)
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        **defaults,
    )


def list_providers() -> list[str]:
    """列出所有已注册的 provider。"""
    return list(PROVIDER_CONFIGS.keys())


def register_provider(
    name: str,
    api_key_key: str,
    base_url_key: str,
    model_key: str,
):
    """运行时注册新 provider（不需要改代码）。

    Args:
        name:          provider 名，如 "zhipu"
        api_key_key:   settings 中的 api_key key
        base_url_key:  settings 中的 base_url key
        model_key:     settings 中的 model key
    """
    PROVIDER_CONFIGS[name] = {
        "api_key_key": api_key_key,
        "base_url_key": base_url_key,
        "model_key": model_key,
    }
