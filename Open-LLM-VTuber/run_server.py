import os
import sys
import atexit
import asyncio
import argparse
import subprocess
from pathlib import Path
import tomli
import uvicorn
from loguru import logger
from upgrade_codes.upgrade_manager import UpgradeManager

from src.open_llm_vtuber.server import WebSocketServer
from src.open_llm_vtuber.config_manager import Config, read_yaml, validate_config

os.environ["HF_HOME"] = str(Path(__file__).parent / "models")
os.environ["MODELSCOPE_CACHE"] = str(Path(__file__).parent / "models")

upgrade_manager = UpgradeManager()

def check_dependencies():
    """
    필수 의존성이 설치되어 있는지 확인.
    패키지 이름과 import 이름이 다른 경우를 처리합니다.
    
    Returns:
        bool: 모든 필수 의존성이 설치되어 있으면 True
    """
    # 맵핑: { "패키지 이름": "실제 임포트할 모듈 이름" }
    # None은 체크를 건너뛰는 패키지 (실행형 도구 등)
    import_map = {
        "duckduckgo-mcp-server": "duckduckgo_mcp_server",
        "letta-client": "letta",
        # "pre-commit": None,  # 실행형 도구라 임포트 체크 제외
        "python-dotenv": "dotenv",
        "pyyaml": "yaml",
        "websocket-client": "websocket",
        "sherpa-onnx": "sherpa_onnx",
        "edge-tts": "edge_tts",
        "azure-cognitiveservices-speech": "azure.cognitiveservices.speech",
        "ruamel-yaml": "ruamel.yaml",
        "python-jose": "jose",
        "pydantic-settings": "pydantic_settings",
    }
    
    # 필수 패키지 목록 (requirements.txt에서 주요 패키지만 체크)
    critical_packages = [
        "fastapi",
        "uvicorn",
        "loguru",
        "numpy",
        "edge-tts",
        "websocket-client",
        "pyyaml",
        "tomli",
        "requests",
        "httpx",
        "openai",
        "anthropic",
    ]
    
    missing_packages = []
    checked_count = 0
    
    logger.info("Checking critical dependencies...")
    
    for package_name in critical_packages:
        # import 이름 결정
        if package_name in import_map:
            import_name = import_map[package_name]
            # None이면 체크 건너뛰기
            if import_name is None:
                continue
        else:
            # 맵핑이 없으면 패키지 이름에서 변환
            # 예: "package-name" -> "package_name", "package.name" -> "package.name"
            import_name = package_name.replace("-", "_")
        
        # 패키지 설치 여부 확인
        try:
            __import__(import_name)
            checked_count += 1
        except ImportError as e:
            missing_packages.append((package_name, import_name))
            logger.warning(f"Missing package: {package_name} (tried to import: {import_name})")
        except Exception:
            # 다른 예외는 일단 설치되어 있다고 간주
            checked_count += 1
    
    if missing_packages:
        logger.error("=" * 60)
        logger.error("Missing critical dependencies:")
        for pkg_name, import_name in missing_packages:
            logger.error(f"  - {pkg_name} (import: {import_name})")
        logger.error("=" * 60)
        logger.error("Please install missing packages:")
        logger.error(f"  pip install -r requirements.txt")
        logger.error("=" * 60)
        return False
    else:
        logger.info(f"✅ All critical dependencies checked ({checked_count} packages)")
        return True

def get_version() -> str:
    with open("pyproject.toml", "rb") as f:
        pyproject = tomli.load(f)
    return pyproject["project"]["version"]


def init_logger(console_log_level: str = "INFO") -> None:
    logger.remove()
    # Console output
    logger.add(
        sys.stderr,
        level=console_log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | {message}",
        colorize=True,
    )

    # File output
    logger.add(
        "logs/debug_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message} | {extra}",
        backtrace=True,
        diagnose=True,
    )


def check_frontend_submodule(lang=None):
    """
    Check if the frontend submodule is initialized. If not, attempt to initialize it.
    If initialization fails, log an error message.
    """
    if lang is None:
        lang = upgrade_manager.lang

    frontend_path = Path(__file__).parent / "frontend" / "index.html"
    if not frontend_path.exists():
        if lang == "zh":
            logger.warning("未找到前端子模块，正在尝试初始化子模块...")
        else:
            logger.warning(
                "Frontend submodule not found, attempting to initialize submodules..."
            )

        try:
            subprocess.run(
                ["git", "submodule", "update", "--init", "--recursive"], check=True
            )
            if frontend_path.exists():
                if lang == "zh":
                    logger.info("👍 前端子模块（和其他子模块）初始化成功。")
                else:
                    logger.info(
                        "👍 Frontend submodule (and other submodules) initialized successfully."
                    )
            else:
                if lang == "zh":
                    logger.critical(
                        '子模块初始化失败。\n你之后可能会在浏览器中看到 {{"detail":"Not Found"}} 的错误提示。请检查我们的快速入门指南和常见问题页面以获取更多信息。'
                    )
                    logger.error(
                        "初始化子模块后，前端文件仍然缺失。\n"
                        + "你是否手动更改或删除了 `frontend` 文件夹？\n"
                        + "它是一个 Git 子模块 - 你不应该直接修改它。\n"
                        + "如果你这样做了，请使用 `git restore frontend` 丢弃你的更改，然后再试一次。\n"
                    )
                else:
                    logger.critical(
                        'Failed to initialize submodules. \nYou might see {{"detail":"Not Found"}} in your browser. Please check our quick start guide and common issues page from our documentation.'
                    )
                    logger.error(
                        "Frontend files are still missing after submodule initialization.\n"
                        + "Did you manually change or delete the `frontend` folder?  \n"
                        + "It's a Git submodule — you shouldn't modify it directly.  \n"
                        + "If you did, discard your changes with `git restore frontend`, then try again.\n"
                    )
        except Exception as e:
            if lang == "zh":
                logger.critical(
                    f'初始化子模块失败: {e}。\n怀疑你跟 GitHub 之间有网络问题。你之后可能会在浏览器中看到 {{"detail":"Not Found"}} 的错误提示。请检查我们的快速入门指南和常见问题页面以获取更多信息。\n'
                )
            else:
                logger.critical(
                    f'Failed to initialize submodules: {e}. \nYou might see {{"detail":"Not Found"}} in your browser. Please check our quick start guide and common issues page from our documentation.\n'
                )


def parse_args():
    parser = argparse.ArgumentParser(description="Open-LLM-VTuber Server")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--hf_mirror", action="store_true", help="Use Hugging Face mirror"
    )
    return parser.parse_args()


@logger.catch
def run(console_log_level: str):
    init_logger(console_log_level)
    logger.info(f"Open-LLM-VTuber, version v{get_version()}")

    # Check critical dependencies before proceeding
    if not check_dependencies():
        logger.critical("Missing critical dependencies. Please install them and try again.")
        sys.exit(1)

    # Get selected language
    lang = upgrade_manager.lang

    # Check if the frontend submodule is initialized
    check_frontend_submodule(lang)

    # Sync user config with default config
    try:
        upgrade_manager.sync_user_config()
    except Exception as e:
        logger.error(f"Error syncing user config: {e}")

    atexit.register(WebSocketServer.clean_cache)

    # Load configurations from yaml file
    config: Config = validate_config(read_yaml("conf.yaml"))
    server_config = config.system_config

    if server_config.enable_proxy:
        logger.info("Proxy mode enabled - /proxy-ws endpoint will be available")

    # Initialize the WebSocket server (synchronous part)
    server = WebSocketServer(config=config)

    # Perform asynchronous initialization (loading context, etc.)
    logger.info("Initializing server context...")
    try:
        asyncio.run(server.initialize())
        logger.info("Server context initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize server context: {e}")
        sys.exit(1)  # Exit if initialization fails

    # Run the Uvicorn server
    logger.info(f"Starting server on {server_config.host}:{server_config.port}")
    uvicorn.run(
        app=server.app,
        host=server_config.host,
        port=server_config.port,
        log_level=console_log_level.lower(),
    )


if __name__ == "__main__":
    args = parse_args()
    console_log_level = "DEBUG" if args.verbose else "INFO"
    if args.verbose:
        logger.info("Running in verbose mode")
    else:
        logger.info(
            "Running in standard mode. For detailed debug logs, use: uv run run_server.py --verbose"
        )
    if args.hf_mirror:
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    run(console_log_level=console_log_level)
