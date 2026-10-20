import argparse
import asyncio
import locale
import os
import signal
import sys

# Windows: Forces the C/C runtime to use UTF-8, solving the problem of sherpa-onnx reading tonal pinyin files with garbled characters
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        locale.setlocale(locale.LC_ALL, ".UTF-8")
    except locale.Error:
        pass

os.environ["QSG_RHI_BACKEND"] = "opengl"
# Force qasync use PySide6
os.environ["QT_API"] = "pyside6"
# Use Basic style to support custom controls
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"

from src.i18n import initialize_language, t  # noqa: E402


def _preparse_language() -> str | None:
    """Read --lang before argparse so help text can be localized."""
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--lang" and index + 1 < len(argv):
            value = argv[index + 1].strip()
            return None if value.lower() == "auto" else value
        if arg.startswith("--lang="):
            value = arg.split("=", 1)[1].strip()
            return None if value.lower() == "auto" else value
    return None


_CLI_LANGUAGE = _preparse_language()
initialize_language(explicit=_CLI_LANGUAGE)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=t("小智"))
    # Run mode selection
    # - gui: graphical interface mode, using PySide6 QML
    # - cli: command line mode, using terminal interaction (lightweight, suitable for screenless/SSH)
    # - tui: full-screen TUI (Textual), editable configuration; requires uv sync --extra tui
    # - gpio: GPIO button mode, only supports Linux (Raspberry Pi), controlled by physical buttons
    parser.add_argument(
        "--mode",
        choices=["gui", "cli", "tui", "gpio"],
        default="gui",
        help=t("运行模式（默认 gui）：gui / cli / tui(全屏终端) / gpio(仅Linux)"),
    )
    parser.add_argument(
        "--protocol",
        choices=["mqtt", "websocket"],
        default="websocket",
        metavar="PROTOCOL",
        help=t("通信协议：mqtt 或 websocket（默认 websocket；须写 --protocol mqtt）"),
    )
    parser.add_argument(
        "--skip-activation",
        action="store_true",
        help=t("跳过激活流程，直接启动应用（仅用于调试）"),
    )
    parser.add_argument(
        "--lang",
        choices=["auto", "zh_CN", "en_US"],
        default="auto",
        help=t("界面语言：auto / zh_CN / en_US（也可设置 XIAOZHI_LANG）"),
    )
    return parser.parse_args()


# Parse parameters first, then initialize configuration and logs (disable ConfigManager lazy singleton)
_args = parse_args()

from src.utils.config_manager import initialize_config  # noqa: E402

_config = initialize_config()
initialize_language(
    explicit=_CLI_LANGUAGE,
    config_value=_config.get_config("SYSTEM_OPTIONS.LANGUAGE", "auto"),
)

from src.logging import load_logging_config, setup_logging  # noqa: E402

# CLI/TUI Mode disables console log output (taken over by the interface)
setup_logging(
    enable_console=(_args.mode not in ("cli", "tui")),
    config=load_logging_config(),
)

from src.bootstrap.container import ServiceContainer  # noqa: E402
from src.logging import get_logger  # noqa: E402

logger = get_logger()


async def handle_activation(mode: str) -> bool:
    """Process the device activation process.

    Args:
        mode: Run mode, "gui", "cli", "tui" or "gpio"

    Returns:
        bool: Whether the activation is successful
    """
    try:
        from src.activation import ActivationService, create_activation_ui

        logger.info(t("开始设备激活流程检查..."))
        activation_service = await ActivationService.create()
        init_result = await activation_service.initialize()

        if not init_result.get("success", False):
            logger.error(t('初始化失败: {value1}', value1=init_result.get('error', t("未知错误"))))
            return False

        if not init_result.get("need_activation_ui", False):
            logger.info(t("设备已激活，无需激活流程"))
            return True

        ui = create_activation_ui(mode, activation_service, init_result)
        return await ui.run()

    except Exception as e:
        logger.error(t('激活流程异常: {value1}', value1=e), exc_info=True)
        return False


async def start_app(mode: str, protocol: str, skip_activation: bool) -> int:
    """Start the unified entrance of the application."""
    global _container  # for SIGINT handling
    logger.info(t('启动{value1}', value1=t("小智")))

    # Process the activation process
    if not skip_activation:
        activation_success = await handle_activation(mode)
        if not activation_success:
            logger.error(t("设备激活失败，程序退出"))
            return 1
    else:
        logger.warning(t("跳过激活流程（调试模式）"))

    # Create and start the application
    _container = ServiceContainer()
    return await _container.run(mode=mode, protocol=protocol)


# Global container reference, used for SIGINT Processing
_container = None


if __name__ == "__main__":
    exit_code = 1
    try:
        # Use parsed parameters
        args = _args

        # detects the Wayland environment and sets the Qt platform plugin configuration
        import os

        is_wayland = (
            os.environ.get("WAYLAND_DISPLAY")
            or os.environ.get("XDG_SESSION_TYPE") == "wayland"
        )

        if args.mode == "gui" and is_wayland:
            if "QT_QPA_PLATFORM" not in os.environ:
                os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"
                logger.info(t("Wayland环境：设置QT_QPA_PLATFORM=wayland;xcb"))
            os.environ.setdefault("QT_WAYLAND_DISABLE_WINDOWDECORATION", "1")
            logger.info(t("Wayland环境检测完成，已应用兼容性配置"))

        # Signal handling
        try:
            if hasattr(signal, "SIGTRAP"):
                signal.signal(signal.SIGTRAP, signal.SIG_IGN)
        except Exception:
            pass

        if args.mode == "gui":
            # GUI mode: Use PySide6 qasync
            try:
                import qasync
                from PySide6.QtWidgets import QApplication
            except ImportError as e:
                logger.error(
                    t("GUI 模式需要 PySide6 + qasync，当前环境未安装。\n请用项目 venv 安装 GUI 依赖后重试：\n  uv sync --extra gui\n  # 或: pip install '.[gui]'\n然后：\n  uv run python main.py\n  # 或: .venv/bin/python main.py\n不要 GUI 时可用：\n  python main.py --mode cli\n  python main.py --mode tui   # 需 uv sync --extra tui\n(原始错误: {value1})", value1=e)
                )
                sys.exit(1)

            qt_app = QApplication.instance() or QApplication(sys.argv)
            qt_app.setQuitOnLastWindowClosed(False)

            loop = qasync.QEventLoop(qt_app)
            asyncio.set_event_loop(loop)
            logger.info(t("已创建 PySide6 + qasync 事件循环"))

            # sets SIGINT signal handling - Request shutdown through TaskManager
            shutdown_state = {"requested": False}

            def handle_sigint(*_):
                if shutdown_state["requested"]:
                    return
                shutdown_state["requested"] = True
                logger.info(t("收到 SIGINT 信号，正在退出..."))

                # Request graceful shutdown through TaskManager
                try:
                    if _container and _container.tasks:
                        _container.tasks.request_shutdown()
                    else:
                        # Container is not ready, exit directly Qt
                        if loop.is_running():
                            loop.call_soon_threadsafe(qt_app.quit)
                except Exception:
                    qt_app.quit()

            signal.signal(signal.SIGINT, handle_sigint)

            try:
                with loop:
                    exit_code = loop.run_until_complete(
                        start_app(args.mode, args.protocol, args.skip_activation)
                    )
            except RuntimeError as e:
                # captures qasync's "Event loop stopped before Future completed" error
                if "Event loop stopped before Future completed" in str(e):
                    logger.debug(t("事件循环已正常终止"))
                    exit_code = 0
                else:
                    raise
        else:
            # CLI / TUI / GPIO: standard asyncio
            if args.mode == "tui":
                try:
                    import textual  # noqa: F401
                except ImportError as e:
                    logger.error(
                        t("TUI 模式需要 textual。请运行:\n  uv sync --extra tui\n  pip install '.[tui]'\n无屏/SSH 请继续用: python main.py --mode cli\n(原始错误: {value1})", value1=e)
                    )
                    sys.exit(1)

            # CLI / GPIO mode: standard asyncio; SIGINT request TaskManager off
            shutdown_state = {"requested": False}

            def handle_sigint_cli(*_):
                if shutdown_state["requested"]:
                    # Quadratic Ctrl C: Hard exit
                    logger.warning(t("再次收到 SIGINT，强制退出"))
                    os._exit(130)
                shutdown_state["requested"] = True
                logger.info(t("收到 SIGINT 信号，正在退出..."))
                try:
                    if _container and _container.tasks:
                        _container.tasks.request_shutdown()
                except Exception:
                    pass

            signal.signal(signal.SIGINT, handle_sigint_cli)
            exit_code = asyncio.run(
                start_app(args.mode, args.protocol, args.skip_activation)
            )

    except KeyboardInterrupt:
        logger.info(t("程序被用户中断"))
        exit_code = 0
    except Exception as e:
        logger.error(t('程序异常退出: {value1}', value1=e), exc_info=True)
        exit_code = 1
    finally:
        sys.exit(exit_code)
