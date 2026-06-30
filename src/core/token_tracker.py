"""Token 统计中间件 — 本地 tiktoken 计数，不依赖 provider 格式。"""
import tiktoken
from typing import List

_DEFAULT_MODEL = "gpt-3.5-turbo"


class TokenTracker:
    """每轮对话的 token 用量统计。"""

    def __init__(self):
        self.encoder = tiktoken.encoding_for_model(_DEFAULT_MODEL)
        self.stats = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "by_node": {}}

    def count_messages(self, messages, node_name: str = "agent") -> int:
        """统计一批消息的 token 数。"""
        cnt = sum(
            len(self.encoder.encode(getattr(m, "content", "") or ""))
            for m in messages
        )
        self.stats["input_tokens"] += cnt
        self.stats["calls"] += 1
        self.stats["by_node"][node_name] = self.stats["by_node"].get(node_name, 0) + cnt
        return cnt

    def count_output(self, text: str) -> int:
        """统计输出 token 数。"""
        c = len(self.encoder.encode(text or ""))
        self.stats["output_tokens"] += c
        return c

    def get_stats(self) -> dict:
        """返回累计统计。"""
        return dict(self.stats)

    def reset(self):
        """重置统计。"""
        self.stats = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "by_node": {}}


# 全局单例
_tracker = None


def get_tracker() -> TokenTracker:
    """获取全局 TokenTracker 单例。"""
    global _tracker
    if _tracker is None:
        _tracker = TokenTracker()
    return _tracker
