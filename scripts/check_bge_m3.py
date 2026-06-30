"""预下载 BGE-M3 权重到本地。不依赖 sentence-transformers，仅用 huggingface_hub。"""
import os
from huggingface_hub import snapshot_download

MODEL_ID = "BAAI/bge-m3"
LOCAL_DIR = os.getenv("BGE_M3_DIR", "models/bge-m3")


def main():
    if os.path.exists(os.path.join(LOCAL_DIR, "config.json")):
        print(f"[ok] BGE-M3 已存在: {LOCAL_DIR}")
        return
    print(f"[..] 下载 BGE-M3 到 {LOCAL_DIR}（约 2GB，首次较慢）...")
    snapshot_download(repo_id=MODEL_ID, local_dir=LOCAL_DIR)
    print(f"[ok] 下载完成: {LOCAL_DIR}")


if __name__ == "__main__":
    main()
