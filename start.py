"""一键启动 AI 陪伴助手（小知）。

支持三种运行模式:
  cli  -- 终端交互对话（默认）
  api  -- FastAPI 控制台 + 前端界面
  wx   -- 微信 Bot 模式（iLink 协议，需扫码登录）

用法:
  python start.py             # 默认 CLI 模式
  python start.py api         # API 模式（含前端）
  python start.py wx          # 微信 Bot 模式
  python start.py --no-docker # 跳过 Docker 服务启动
  python start.py stop        # 停止所有服务
  python start.py clean       # 清理 Docker 数据目录（慎用）
"""
import os
import sys
import time
import subprocess
import signal
import shutil
import platform

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
# ponytail: cross-platform venv path
_IS_WIN = sys.platform == "win32"
_VENV_BIN = "Scripts" if _IS_WIN else "bin"
_VENV_PYTHON_EXE = "python.exe" if _IS_WIN else "python"
VENV_PYTHON = os.path.join(PROJECT_DIR, ".venv", _VENV_BIN, _VENV_PYTHON_EXE)
MAIN_PY = os.path.join(PROJECT_DIR, "src", "core", "main.py")
SERVER_PY = os.path.join(PROJECT_DIR, "src", "api", "server.py")
DATA_DIR = os.path.join(PROJECT_DIR, "data")
ENV_FILE = os.path.join(PROJECT_DIR, ".env")


# ── 工具函数 ────────────────────────────────────────────────────

def run_cmd(cmd, cwd=None, check=True):
    """执行 shell 命令，返回 CompletedProcess。"""
    result = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"[FAIL] 命令: {cmd}")
        print(f"  stderr: {result.stderr.strip()}")
        sys.exit(1)
    return result


def ensure_venv():
    """确保 .venv 存在且依赖已安装。"""
    if not os.path.exists(VENV_PYTHON):
        print("[SETUP] 虚拟环境不存在，正在创建...")
        system_python = sys.executable
        run_cmd(f"{system_python} -m venv {os.path.join(PROJECT_DIR, '.venv')}")
        print("[SETUP] 虚拟环境已创建")

    # 检查关键依赖是否已安装
    check_result = run_cmd(
        f"{VENV_PYTHON} -c \"import langgraph, fastapi, uvicorn\"",
        check=False
    )
    if check_result.returncode != 0:
        print("[SETUP] 安装项目依赖...")
        pip = os.path.join(PROJECT_DIR, ".venv", _VENV_BIN, "pip.exe" if _IS_WIN else "pip")
        req_file = os.path.join(PROJECT_DIR, "requirements.txt")
        if os.path.exists(req_file):
            run_cmd(f"{pip} install -r {req_file} -i https://pypi.tuna.tsinghua.edu.cn/simple")
        else:
            run_cmd(f"{pip} install -e {PROJECT_DIR} -i https://pypi.tuna.tsinghua.edu.cn/simple")
        print("[SETUP] 依赖安装完成")


def ensure_data_dirs():
    """确保 data 子目录存在。"""
    for subdir in ["sqlite", "qdrant_storage", "neo4j_data"]:
        path = os.path.join(DATA_DIR, subdir)
        os.makedirs(path, exist_ok=True)


# ── Docker 管理 ─────────────────────────────────────────────────

def check_docker():
    """检查 Docker 是否可用。"""
    try:
        result = run_cmd("docker --version", check=False)
        return result.returncode == 0
    except Exception:
        return False


def start_docker_services():
    """启动 Qdrant + Neo4j 容器。"""
    print("[DOCKER] 启动数据库服务 (Qdrant + Neo4j)...")
    run_cmd("docker-compose up -d", cwd=PROJECT_DIR)
    print("[DOCKER] 等待服务就绪...")
    time.sleep(5)

    # 简单健康检查
    for service, port in [("Qdrant", "6333"), ("Neo4j", "7687")]:
        result = run_cmd(
            f"python -c \"import socket; s=socket.socket(); s.settimeout(2); "
            f"s.connect(('localhost',{port})); s.close(); print('OK')\"",
            check=False
        )
        status = "OK" if result.returncode == 0 else "NOT READY"
        print(f"  {service} ({port}): {status}")


def stop_docker_services():
    """停止 Docker 容器。"""
    print("[DOCKER] 停止数据库服务...")
    run_cmd("docker-compose down", cwd=PROJECT_DIR, check=False)
    print("[DOCKER] 服务已停止")


def clean_docker_data():
    """清理 Docker 数据目录（危险操作，需二次确认）。"""
    print("[WARN] 此操作将删除所有 Qdrant 向量数据和 Neo4j 图谱数据！")
    confirm = input("确认清理？输入 YES 继续: ").strip()
    if confirm != "YES":
        print("已取消")
        return

    stop_docker_services()

    for subdir in ["qdrant_storage", "neo4j_data"]:
        path = os.path.join(DATA_DIR, subdir)
        if os.path.exists(path):
            shutil.rmtree(path)
            print(f"  已删除: {path}")

    ensure_data_dirs()
    print("[DONE] 数据已清理，重新启动将初始化空数据库")


# ── 模式启动 ────────────────────────────────────────────────────

def start_cli():
    """启动 CLI 交互对话模式。"""
    print("[APP] 启动 AI 陪伴助手 (CLI 模式)...")

    proc = subprocess.Popen([VENV_PYTHON, MAIN_PY], cwd=PROJECT_DIR)

    def signal_handler(sig, frame):
        print("\n[APP] 正在关闭...")
        proc.terminate()
        proc.wait(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    proc.wait()


def start_api():
    """启动 FastAPI 控制台模式（含前端界面）。"""
    # 读取 API_PORT
    port = "8000"
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("API_PORT="):
                    port = line.split("=", 1)[1].strip()

    print(f"[APP] 启动 AI 陪伴助手 (API 模式, http://localhost:{port})...")
    print(f"  前端界面: http://localhost:{port}")
    print(f"  API 文档: http://localhost:{port}/docs")

    proc = subprocess.Popen(
        [VENV_PYTHON, "-m", "src.api.server"],
        cwd=PROJECT_DIR
    )

    def signal_handler(sig, frame):
        print("\n[APP] 正在关闭...")
        proc.terminate()
        proc.wait(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    proc.wait()


def start_wx():
    """启动微信 Bot 模式（iLink 协议，需扫码登录）。"""
    print("[APP] 启动 AI 陪伴助手 (微信 Bot 模式)...")

    WX_MAIN_PY = os.path.join(PROJECT_DIR, "src", "weixin", "bot.py")

    proc = subprocess.Popen([VENV_PYTHON, WX_MAIN_PY], cwd=PROJECT_DIR)

    def signal_handler(sig, frame):
        print("\n[APP] 正在关闭...")
        proc.terminate()
        proc.wait(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    proc.wait()


def stop_all():
    """停止所有正在运行的服务。"""
    print("[STOP] 停止所有服务...")
    # 尝试关闭可能的 CLI/API/WX 进程
    WX_MAIN_PY = os.path.join(PROJECT_DIR, "src", "weixin", "bot.py")
    for script in [MAIN_PY, SERVER_PY, WX_MAIN_PY]:
        if platform.system() == "Windows":
            run_cmd(
                f"wmic process where \"CommandLine like '%{script.replace(os.sep, '/')}'\" "
                f"call terminate",
                check=False
            )
        else:
            run_cmd(f"pkill -f {script}", check=False)

    stop_docker_services()
    print("[STOP] 所有服务已停止")


# ── 主入口 ──────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    mode = "cli"
    skip_docker = False

    # 解析参数
    for arg in args:
        if arg in ("api", "API"):
            mode = "api"
        elif arg in ("--no-docker", "--skip-docker"):
            skip_docker = True
        elif arg == "stop":
            stop_all()
            return
        elif arg == "clean":
            clean_docker_data()
            return
        elif arg in ("cli", "CLI"):
            mode = "cli"
        elif arg in ("wx", "WX", "wechat", "WECHAT"):
            mode = "wx"

    os.chdir(PROJECT_DIR)

    # Step 1: 确保环境就绪
    print("=" * 50)
    print("  小知 - AI 陪伴助手")
    print("=" * 50)
    print(f"[MODE] 运行模式: {mode.upper()}")

    ensure_venv()
    ensure_data_dirs()

    # Step 2: Docker 服务
    if not skip_docker:
        if check_docker():
            start_docker_services()
        else:
            print("[WARN] Docker 未安装或未运行，向量/图谱功能将不可用")
            print("  提示: 安装 Docker Desktop 或使用 --no-docker 跳过")

    # Step 3: 启动应用
    if mode == "wx":
        start_wx()
    elif mode == "api":
        start_api()
    else:
        start_cli()


if __name__ == "__main__":
    main()
