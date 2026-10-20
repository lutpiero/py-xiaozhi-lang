"""CLI terminal display interface.

Provides terminal TUI Interface, including:
- Status dashboard (top frame)
- Log display area
- Command input area
"""
import asyncio
import logging
import os
import shutil
import sys
from collections import deque
from typing import Callable, Optional

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


class CLIDisplay:
    """CLI terminal display interface."""

    def __init__(self):
        self.running = True
        self._use_ansi = sys.stdout.isatty()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_drawn_rows = 0
        self._render_lock = None
        self._initialized = False  # has been initialized
        self._log_handler_installed = False  # Whether the log processor has been installed

        # Dashboard data
        self._dash_status = t("待命")
        self._dash_connected = False
        self._dash_text = ""
        self._dash_music = ""
        self._dash_emotion = "neutral"
        self._dash_auto_mode = False

        # Layout settings
        self._input_area_lines = 3  # Input area line number
        self._dashboard_lines = 9  # The minimum number of lines in the display area

        # ANSI style
        self._ansi = {
            "reset": "\x1b[0m",
            "bold": "\x1b[1m",
            "dim": "\x1b[2m",
            "blue": "\x1b[34m",
            "cyan": "\x1b[36m",
            "green": "\x1b[32m",
            "yellow": "\x1b[33m",
            "magenta": "\x1b[35m",
            "red": "\x1b[31m",
        }

        # Callback function
        self._on_command: Optional[Callable[[str], None]] = None

        # Whether the log buffer
        self._log_lines: deque[str] = deque(maxlen=6)

        # Command queue
        self._command_queue: asyncio.Queue = asyncio.Queue()

    def set_command_callback(self, callback: Callable[[str], None]):
        """Set the command callback."""
        self._on_command = callback

    def intercept_logging(self):
        """Intercept log output as early as possible (called before start).

        mimics the old implementation: in The __init__ phase removes the StreamHandler and installs the custom handler.
        """
        # Remove all StreamHandlers first
        self._remove_stream_handlers()
        # Reinstall our log processor
        self._install_log_handler()

    async def start(self):
        """Start CLI Display."""
        # Get event loop first
        self._loop = asyncio.get_running_loop()
        self._render_lock = asyncio.Lock()

        # Make sure the log has been intercepted (if intercept_logging has not been called yet)
        if not self._log_handler_installed:
            self.intercept_logging()

        # Clear the screen and initialize the interface
        if self._use_ansi:
            # Clear the screen completely: Clear the screen Clear the scroll buffer Cursor moves to upper left corner
            sys.stdout.write("\x1b[3J\x1b[2J\x1b[H")
            sys.stdout.flush()

        # flag initialized
        self._initialized = True

        # Initialization screen display
        await self._init_screen()

        # Start input loop
        try:
            await self._keyboard_input_loop()
        except asyncio.CancelledError:
            pass

    async def close(self):
        """Close CLI Display."""
        self.running = False

        # Restore standard log
        self._restore_logging()

        # Clear the screen
        if self._use_ansi:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()

        print(t("正在关闭应用...\n"))

    # ========== Status update ==========

    def update_status(self, status: str, connected: bool = True):
        """Update status."""
        self._dash_status = status
        self._dash_connected = connected
        self._schedule_render()

    def update_text(self, text: str):
        if text and text.strip():
            self._dash_text = text.strip()
            self._schedule_render()

    def update_music_line(self, text: str):
        self._dash_music = (text or "").strip()
        self._schedule_render()

    def update_emotion(self, emotion: str):
        """Update expression."""
        self._dash_emotion = emotion
        self._schedule_render()

    def update_auto_mode(self, auto_mode: bool):
        """Update auto mode status."""
        self._dash_auto_mode = auto_mode
        self._schedule_render()

    def add_log(self, message: str):
        """Add log."""
        self._log_lines.append(message)
        self._schedule_render()

    def _schedule_render(self):
        """Scheduling rendering."""
        if not self._initialized:
            return
        if self._loop and self._use_ansi and self.running:
            try:
                if self._loop.is_running():
                    self._loop.call_soon_threadsafe(self._do_render)
            except Exception as e:
                logging.getLogger(__name__).error(t('调度渲染失败: {value1}', value1=e))

    def _do_render(self):
        """Performs rendering (called in event loop)."""
        if not self._initialized:
            return
        try:
            task = asyncio.create_task(self._safe_render(), name="cli:render")

            def _on_done(t: asyncio.Task):
                if t.cancelled():
                    return
                exc = t.exception()
                if exc:
                    logging.getLogger(__name__).error(
                        t('CLI 渲染任务异常: {value1}', value1=exc), exc_info=exc
                    )

            task.add_done_callback(_on_done)
        except Exception as e:
            logging.getLogger(__name__).error(t('创建渲染任务失败: {value1}', value1=e), exc_info=True)

    async def _safe_render(self):
        """Safe rendering (with lock)."""
        if self._render_lock is None:
            return
        async with self._render_lock:
            await self._render_dashboard()

    # ========== Screen rendering ==========

    async def _init_screen(self):
        """Initialization screen."""
        # Note: Clearing the screen has been completed in start()
        await self._render_dashboard(full=True)
        await self._render_input_area()

    async def _render_dashboard(self, full: bool = False):
        """Render the dashboard."""

        def trunc(s: str, limit: int = 60) -> str:
            return s if len(s) <= limit else s[: limit - 1] + "…"

        # Build Status line
        mode_text = t("自动") if self._dash_auto_mode else t("手动")
        conn_text = t("已连接") if self._dash_connected else t("未连接")

        lines = [
            t("状态: {status}", status=trunc(self._dash_status)),
            t("连接: {connected} | 模式: {mode}", connected=conn_text, mode=mode_text),
            t("表情: {emotion}", emotion=self._dash_emotion),
            t("对话: {text}", text=trunc(self._dash_text)),
            t("音乐: {music}", music=trunc(self._dash_music) if self._dash_music else "—"),
        ]

        # does not display the log line (the log is still intercepted, but is not displayed on the interface)

        if not self._use_ansi:
            print(f"\r{lines[0]}        ", end="", flush=True)
            return

        cols, rows = self._term_size()
        usable_rows = max(5, rows - self._input_area_lines)

        # style function
        def style(s: str, *names: str) -> str:
            if not self._use_ansi:
                return s
            prefix = "".join(self._ansi.get(n, "") for n in names)
            return f"{prefix}{s}{self._ansi['reset']}"

        title = style(f" {t('小智')} ", "bold", "cyan")

        # framework
        top_bar = "┌" + ("─" * (max(2, cols - 2))) + "┐"
        title_line = "│" + title.center(max(2, cols - 2) + 14) + "│"  # 14 Compensation ANSI
        sep_line = "├" + ("─" * (max(2, cols - 2))) + "┤"
        bottom_bar = "└" + ("─" * (max(2, cols - 2))) + "┘"

        # Content area
        body_rows = max(1, usable_rows - 4)
        body = []
        for i in range(body_rows):
            if i < len(lines):
                text = lines[i]
                if i == 0:
                    text = style(text, "green")
                elif i == 1:
                    text = style(text, "cyan")
                elif "INFO" in text or "DEBUG" in text:
                    text = style(text, "dim")
                elif "ERROR" in text or "WARNING" in text:
                    text = style(text, "yellow")
            else:
                text = ""
            body.append("│" + text.ljust(max(2, cols - 2))[: max(2, cols - 2)] + "│")

        # Save the cursor
        sys.stdout.write("\x1b7")

        # Clear the old area
        total_rows = 4 + body_rows
        rows_to_clear = max(self._last_drawn_rows, total_rows)
        for i in range(rows_to_clear):
            self._goto(1 + i, 1)
            sys.stdout.write("\x1b[2K")

        # Draw
        self._goto(1, 1)
        sys.stdout.write("\x1b[2K" + top_bar[:cols])
        self._goto(2, 1)
        sys.stdout.write("\x1b[2K" + title_line[:cols])
        self._goto(3, 1)
        sys.stdout.write("\x1b[2K" + sep_line[:cols])

        for idx in range(body_rows):
            self._goto(4 + idx, 1)
            sys.stdout.write("\x1b[2K")
            sys.stdout.write(body[idx][:cols])

        self._goto(4 + body_rows, 1)
        sys.stdout.write("\x1b[2K" + bottom_bar[:cols])

        # Restore cursor
        sys.stdout.write("\x1b8")
        sys.stdout.flush()

        self._last_drawn_rows = total_rows

    async def _render_input_area(self):
        """Render the input area."""
        if not self._use_ansi:
            return

        cols, rows = self._term_size()
        separator_row = max(1, rows - self._input_area_lines + 1)
        first_input_row = min(rows, separator_row + 1)
        second_input_row = min(rows, separator_row + 2)

        sys.stdout.write("\x1b7")

        # Separator
        self._goto(separator_row, 1)
        sys.stdout.write("\x1b[2K")
        sys.stdout.write("═" * max(1, cols))

        # Input prompt
        self._goto(first_input_row, 1)
        sys.stdout.write("\x1b[2K")
        prompt_plain = t("输入: ")
        prompt = f"\x1b[1m\x1b[36m{prompt_plain}\x1b[0m " if self._use_ansi else prompt_plain
        sys.stdout.write(prompt)

        # Reserved lines
        self._goto(second_input_row, 1)
        sys.stdout.write("\x1b[2K")
        sys.stdout.flush()

        sys.stdout.write("\x1b8")
        self._goto(first_input_row, 1)
        sys.stdout.write(prompt)
        sys.stdout.flush()

    def _clear_input_area(self):
        """Clear the input area."""
        if not self._use_ansi:
            return
        cols, rows = self._term_size()
        separator_row = max(1, rows - self._input_area_lines + 1)
        for r in range(separator_row, min(rows + 1, separator_row + 3)):
            self._goto(r, 1)
            sys.stdout.write("\x1b[2K")
        sys.stdout.flush()

    # ========== Input processing ==========

    async def _keyboard_input_loop(self):
        """Keyboard input loop."""
        try:
            while self.running:
                if self._use_ansi:
                    await self._render_input_area()
                    cmd = await asyncio.to_thread(self._read_line_raw)
                    self._clear_input_area()
                    await self._render_dashboard()
                else:
                    cmd = await asyncio.to_thread(input, t("输入: "))

                await self._handle_command(cmd.strip())
        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            await self.close()

    def _read_line_raw(self) -> str:
        """Raw mode read input (supports Chinese)."""
        try:
            import termios
            import tty
        except ImportError:
            # Windows not supported termios
            return input()

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            buffer: list[str] = []
            while True:
                ch = os.read(fd, 4)
                if not ch:
                    break
                try:
                    s = ch.decode("utf-8")
                except UnicodeDecodeError:
                    while True:
                        ch += os.read(fd, 1)
                        try:
                            s = ch.decode("utf-8")
                            break
                        except UnicodeDecodeError:
                            continue

                if s in ("\r", "\n"):
                    sys.stdout.write("\r\n")
                    sys.stdout.flush()
                    break
                elif s in ("\x7f", "\b"):
                    if buffer:
                        buffer.pop()
                    self._redraw_input_line("".join(buffer))
                elif s == "\x03":  # Ctrl+C
                    raise KeyboardInterrupt
                else:
                    buffer.append(s)
                    self._redraw_input_line("".join(buffer))

            return "".join(buffer)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def _redraw_input_line(self, content: str):
        """Redraw input lines."""
        cols, rows = self._term_size()
        separator_row = max(1, rows - self._input_area_lines + 1)
        first_input_row = min(rows, separator_row + 1)
        prompt_plain = t("输入: ")
        prompt = f"\x1b[1m\x1b[36m{prompt_plain}\x1b[0m " if self._use_ansi else prompt_plain
        self._goto(first_input_row, 1)
        sys.stdout.write("\x1b[2K")
        visible = content
        max_len = max(1, cols - len(t("输入: ")) - 1)
        if len(visible) > max_len:
            visible = visible[-max_len:]
        sys.stdout.write(f"{prompt}{visible}")
        sys.stdout.flush()

    async def _handle_command(self, cmd: str):
        """Process commands - all forwarded to CliViewManager."""
        if not cmd:
            return

        if self._on_command:
            # All commands forwarded, not intercepted
            self._on_command(cmd)

    def show_help(self):
        """Display help."""
        self._dash_text = t("命令: r=开始/停止 | x=打断 | q=退出 | h=帮助 | 其他=发送文本")
        self._schedule_render()

    # ========== Log processing ==========

    def _install_log_handler(self):
        """Install the log processor."""
        # Prevent repeated installations
        if self._log_handler_installed:
            return
        self._log_handler_installed = True

        class DisplayLogHandler(logging.Handler):
            def __init__(self, display: "CLIDisplay"):
                super().__init__()
                self.display = display

            def emit(self, record: logging.LogRecord):
                try:
                    msg = self.format(record)
                    self.display._log_lines.append(msg)
                    self.display._schedule_render()
                except Exception as e:
                    logging.getLogger(__name__).error(t('日志记录失败: {value1}', value1=e))

        handler = DisplayLogHandler(self)
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logging.getLogger().addHandler(handler)

    def _remove_stream_handlers(self):
        """Remove all log handlers for standard output."""
        root = logging.getLogger()

        # Remove all StreamHandler
        for h in list(root.handlers):
            if isinstance(h, logging.StreamHandler):
                root.removeHandler(h)

        # Remove all registered loggers StreamHandler
        for name in list(logging.Logger.manager.loggerDict.keys()):
            log = logging.getLogger(name)
            for h in list(log.handlers):
                if isinstance(h, logging.StreamHandler):
                    log.removeHandler(h)

        # Set the root logger Level
        root.setLevel(logging.DEBUG)

    def _restore_logging(self):
        """Restore standard log."""
        root = logging.getLogger()

        # Remove DisplayLogHandler
        for h in list(root.handlers):
            if h.__class__.__name__ == "DisplayLogHandler":
                root.removeHandler(h)

        # Add simple StreamHandler
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.WARNING)
        handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
        root.addHandler(handler)

    # ========== Utility functions ==========

    def _goto(self, row: int, col: int = 1):
        """Move the cursor."""
        sys.stdout.write(f"\x1b[{max(1, row)};{max(1, col)}H")

    def _term_size(self) -> tuple[int, int]:
        """Get the terminal size."""
        try:
            size = shutil.get_terminal_size(fallback=(80, 24))
            return size.columns, size.lines
        except Exception:
            return 80, 24
