"""集中配置管理 -- 所有 env 读取从这里走，方便测试和 mock。

新增能力（前端控制台对接）:
  write_env(key, value)  -- 写 .env 保留注释，按行改写
  mask_secret(value)     -- API Key 脱敏，只露前4位
  get_settings()         -- 缓存读，clear 后重读
  ENV_FILE               -- .env 文件路径，方便外部引用
"""
from functools import lru_cache
from dotenv import load_dotenv
import os

ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

load_dotenv(ENV_FILE)


# ── .env 参数名映射（Python key -> .env 变量名）──────────────────
_ENV_KEY_MAP = {
    "llm_provider": "LLM_PROVIDER",
    "volcengine_api_key": "VOLCENGINE_API_KEY",
    "volcengine_base_url": "VOLCENGINE_BASE_URL",
    "volcengine_model": "VOLCENGINE_MODEL",
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "deepseek_base_url": "DEEPSEEK_BASE_URL",
    "deepseek_model": "DEEPSEEK_MODEL",
    "openai_api_key": "OPENAI_API_KEY",
    "openai_base_url": "OPENAI_BASE_URL",
    "openai_model": "MODEL_NAME",
    "sqlite_path": "SQLITE_PATH",
    "qdrant_host": "QDRANT_HOST",
    "qdrant_port": "QDRANT_PORT",
    "neo4j_uri": "NEO4J_URI",
    "neo4j_user": "NEO4J_USER",
    "neo4j_password": "NEO4J_PASSWORD",
    "embedding_model": "EMBEDDING_MODEL",
    "bge_m3_dir": "BGE_M3_DIR",
    "enable_scheduler": "ENABLE_SCHEDULER",
    "idle_threshold_minutes": "IDLE_THRESHOLD_MINUTES",
    "scheduler_timezone": "SCHEDULER_TIMEZONE",
    "scheduler_max_workers": "SCHEDULER_MAX_WORKERS",
    "scheduler_coalesce": "SCHEDULER_COALESCE",
    "scheduler_max_instances": "SCHEDULER_MAX_INSTANCES",
    "scheduler_jobs_db": "SCHEDULER_JOBS_DB",
    "scheduler_monitoring": "SCHEDULER_MONITORING",
    "morning_greeting_hour": "MORNING_GREETING_HOUR",
    "morning_greeting_minute": "MORNING_GREETING_MINUTE",
    "morning_greeting_misfire_grace": "MORNING_GREETING_MISFIRE_GRACE",
    "reminder_misfire_grace": "REMINDER_MISFIRE_GRACE",
    # 微信 Bot 配置
    "wx_base_url": "WX_BASE_URL",
    "wx_bot_type": "WX_BOT_TYPE",
    "wx_poll_timeout": "WX_POLL_TIMEOUT",
    "wx_max_concurrent": "WX_MAX_CONCURRENT",
    "wx_channel_version": "WX_CHANNEL_VERSION",
    "api_port": "API_PORT",
}

# ── 需脱敏的 key（API Key 类）──────────────────────────────────
_SECRET_KEYS = {
    "volcengine_api_key", "deepseek_api_key",
    "openai_api_key", "neo4j_password",
}


def mask_secret(value: str) -> str:
    """API Key 脱敏：只露前4位，其余用 **** 替代。"""
    if not value or len(value) <= 4:
        return "****" if value else ""
    return value[:4] + "****"


def write_env(updates: dict) -> list:
    """写 .env 文件，保留注释和空行，按行改写。

    updates: { env_var_name: new_value, ... }
    返回: [被改写的 env_var_name 列表]

    注意：只改值，不改注释；不存在的新变量追加到文件末尾。
    """
    env_var_names = {v: k for k, v in _ENV_KEY_MAP.items()}  # 反转映射

    if not os.path.exists(ENV_FILE):
        # .env 不存在，直接写全部
        lines = []
        for env_var, value in updates.items():
            lines.append(f"{env_var}={value}")
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return list(updates.keys())

    with open(ENV_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated = []
    existing_vars = set()

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            var_name = stripped.split("=", 1)[0].strip()
            existing_vars.add(var_name)
            if var_name in updates:
                new_value = updates[var_name]
                lines[i] = f"{var_name}={new_value}\n"
                updated.append(var_name)

    # 追加不存在的新变量
    for env_var, value in updates.items():
        if env_var not in existing_vars:
            lines.append(f"{env_var}={value}\n")
            updated.append(env_var)

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # 写后清除缓存，下次 get_settings() 重新读取
    get_settings.cache_clear()
    # re-inject .env values into os.environ（否则 os.getenv() 仍返回旧值）
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=True)

    # ponytail: 非原子写（无 fcntl.flock on Windows），并发写以最后一次为准
    return updated


@lru_cache(maxsize=1)
def get_settings() -> dict:
    """读取所有配置，结果缓存。改 .env 后需调用 get_settings.cache_clear() 重读。"""
    return {
        # -- LLM --
        "llm_provider": os.getenv("LLM_PROVIDER", ""),
        "volcengine_api_key": os.getenv("VOLCENGINE_API_KEY", ""),
        "volcengine_base_url": os.getenv(
            "VOLCENGINE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
        ),
        "volcengine_model": os.getenv(
            "VOLCENGINE_MODEL", "doubao-seed-2-0-lite-260215"
        ),
        "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "deepseek_base_url": os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
        ),
        "deepseek_model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "openai_base_url": os.getenv("OPENAI_BASE_URL", ""),
        "openai_model": os.getenv("MODEL_NAME", "gpt-3.5-turbo"),
        # -- 存储 --
        "sqlite_path": os.getenv("SQLITE_PATH", "data/sqlite/companion.db"),
        "qdrant_host": os.getenv("QDRANT_HOST", "localhost"),
        "qdrant_port": int(os.getenv("QDRANT_PORT", "6333")),
        "neo4j_uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        "neo4j_user": os.getenv("NEO4J_USER", "neo4j"),
        "neo4j_password": os.getenv("NEO4J_PASSWORD", "test1234"),
        # -- 向量模型 --
        "embedding_model": os.getenv(
            "EMBEDDING_MODEL", "BAAI/bge-m3"
        ),
        "bge_m3_dir": os.getenv("BGE_M3_DIR", "models/bge-m3"),
        # -- 主动调度 --
        "enable_scheduler": os.getenv("ENABLE_SCHEDULER", "false").lower() == "true",
        "idle_threshold_minutes": int(os.getenv("IDLE_THRESHOLD_MINUTES", "30")),
        #  调度器核心参数
        "scheduler_timezone": os.getenv("SCHEDULER_TIMEZONE", "Asia/Shanghai"),
        "scheduler_max_workers": int(os.getenv("SCHEDULER_MAX_WORKERS", "30")),
        "scheduler_coalesce": os.getenv("SCHEDULER_COALESCE", "true").lower() == "true",
        "scheduler_max_instances": int(os.getenv("SCHEDULER_MAX_INSTANCES", "1")),
        "scheduler_jobs_db": os.getenv("SCHEDULER_JOBS_DB", "data/sqlite/jobs.sqlite"),
        "scheduler_monitoring": os.getenv("SCHEDULER_MONITORING", "true").lower() == "true",
        #  早安问候时间
        "morning_greeting_hour": int(os.getenv("MORNING_GREETING_HOUR", "9")),
        "morning_greeting_minute": int(os.getenv("MORNING_GREETING_MINUTE", "0")),
        "morning_greeting_misfire_grace": int(os.getenv("MORNING_GREETING_MISFIRE_GRACE", "86400")),
        #  提醒宽限期
        "reminder_misfire_grace": int(os.getenv("REMINDER_MISFIRE_GRACE", "3600")),
        # -- 微信 Bot (v2.3 新增) --
        "wx_base_url": os.getenv("WX_BASE_URL", "https://ilinkai.weixin.qq.com"),
        "wx_bot_type": os.getenv("WX_BOT_TYPE", "3"),
        "wx_poll_timeout": int(os.getenv("WX_POLL_TIMEOUT", "35")),
        "wx_max_concurrent": int(os.getenv("WX_MAX_CONCURRENT", "10")),
        "wx_channel_version": os.getenv("WX_CHANNEL_VERSION", "1.0.3"),
    }
