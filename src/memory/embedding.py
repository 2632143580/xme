
import os
import warnings
from functools import lru_cache
from typing import List, Optional

# 国内用户：通过镜像加速 HuggingFace 下载
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from src.config import get_settings


@lru_cache(maxsize=1)
def get_embedder():
    """懒加载 BGE-M3 模型，结果缓存。"""
    s = get_settings()
    model_name = s["embedding_model"]

    # 尝试从本地加载
    local_dir = os.getenv("BGE_M3_DIR", "models/bge-m3")
    if os.path.exists(local_dir) and os.path.exists(os.path.join(local_dir, "config.json")):
        from sentence_transformers import SentenceTransformer
        print(f"[embedding] 加载本地模型: {local_dir}")
        return SentenceTransformer(local_dir)

    # 尝试在线加载（会自动下载到 cache）
    try:
        from sentence_transformers import SentenceTransformer
        print(f"[embedding] 在线加载模型: {model_name}（首次会下载约 2GB）")
        model = SentenceTransformer(model_name)
        # 保存到本地
        os.makedirs(local_dir, exist_ok=True)
        model.save(local_dir)
        print(f"[embedding] 模型已缓存到: {local_dir}")
        return model
    except Exception as e:
        warnings.warn(f"[warn] BGE-M3 加载失败，向量检索降级：{e}")
        return None


def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    """向量化多段文本。返回 List[vector]，失败返回 None。"""
    model = get_embedder()
    if model is None:
        return None
    try:
        vectors = model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()
    except Exception as e:
        warnings.warn(f"[warn] 向量化失败：{e}")
        return None


def embed_query(query: str) -> Optional[List[float]]:
    """向量化单条查询（用 BGE-M3 的 query 指令格式）。"""
    model = get_embedder()
    if model is None:
        return None
    try:
        # BGE-M3 建议对查询加上指令前缀
        texts = [f"为这个句子生成表示以用于检索相关文章：{query}"]
        vectors = model.encode(texts, normalize_embeddings=True)
        return vectors[0].tolist()
    except Exception as e:
        warnings.warn(f"[warn] 查询向量化失败：{e}")
        return None
