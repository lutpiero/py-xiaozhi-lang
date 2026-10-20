"""Log processor module.

Provide:
- Dual rotation file processor (time size)
- Asynchronous log processor
"""
import atexit
import gzip
import logging
import queue
import shutil
import time
from logging.handlers import BaseRotatingHandler, QueueHandler, QueueListener
from pathlib import Path
from typing import Union

from src.i18n import t


class TimeSizeRotatingFileHandler(BaseRotatingHandler):
    """Dual rotation file processor.

    Supports rotation by time and size at the same time. The rotation will be executed first if either condition is triggered.
    """

    def __init__(
        self,
        filename: Union[str, Path],
        when: str = "midnight",
        interval: int = 1,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 30,
        encoding: str = "utf-8",
        delay: bool = False,
        compress: bool = False,
    ) -> None:
        self.baseFilename = str(filename)
        self.when = when.upper()
        self.interval = interval
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.compress = compress

        # Time rotation calculation
        self._compute_rollover_time()

        # Initialize the parent class
        super().__init__(self.baseFilename, "a", encoding=encoding, delay=delay)

    def _compute_rollover_time(self) -> None:
        """
        Calculate next rotation time.
        """
        current_time = int(time.time())

        if self.when == "MIDNIGHT":
            # Calculate seconds to midnight
            t = time.localtime(current_time)
            current_hour = t.tm_hour
            current_minute = t.tm_min
            current_second = t.tm_sec
            seconds_to_midnight = (
                (24 - current_hour - 1) * 3600
                + (60 - current_minute - 1) * 60
                + (60 - current_second)
            )
            self.rollover_at = current_time + seconds_to_midnight
            self.suffix = "%Y-%m-%d"
        elif self.when == "H":
            self.rollover_at = current_time + 3600 * self.interval
            self.suffix = "%Y-%m-%d_%H"
        elif self.when == "D":
            self.rollover_at = current_time + 86400 * self.interval
            self.suffix = "%Y-%m-%d"
        else:
            self.rollover_at = current_time + 86400
            self.suffix = "%Y-%m-%d"

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        """
        Check whether it is needed Rotation.
        """
        # Check the time
        if time.time() >= self.rollover_at:
            return True

        # Check the size
        if self.max_bytes > 0:
            if self.stream is None:
                self.stream = self._open()
            try:
                self.stream.seek(0, 2)  # Move to end of file
                if self.stream.tell() + len(self.format(record)) >= self.max_bytes:
                    return True
            except (OSError, ValueError):
                pass

        return False

    def doRollover(self) -> None:
        """
        Perform rotation.
        """
        if self.stream:
            self.stream.close()
            self.stream = None

        # Generate rotation file names
        current_time = time.time()
        time_suffix = time.strftime(self.suffix, time.localtime(current_time))

        # Check whether it is a size-triggered rotation (possibly multiple times on the same day)
        base_path = Path(self.baseFilename)
        base_name = base_path.stem
        base_ext = base_path.suffix
        parent = base_path.parent

        # Build rotation file name
        rotated_name = f"{base_name}.{time_suffix}"

        # If the file with the same name already exists, add the serial number
        counter = 0
        while True:
            if counter == 0:
                dfn = parent / f"{rotated_name}{base_ext}"
            else:
                dfn = parent / f"{rotated_name}.{counter}{base_ext}"

            if self.compress:
                dfn = Path(str(dfn) + ".gz")

            if not dfn.exists():
                break
            counter += 1

        # Execute rotation
        source_path = Path(self.baseFilename)
        if source_path.exists():
            if self.compress:
                self._compress_file(source_path, dfn)
                source_path.unlink()
            else:
                shutil.move(str(source_path), str(dfn))

        # Clean up old files
        self._cleanup_old_files(parent, base_name)

        # Recalculate next rotation time
        self._compute_rollover_time()

        # Reopen file
        if not self.delay:
            self.stream = self._open()

    def _compress_file(self, source: Path, dest: Path) -> None:
        """
        Compress files.
        """
        with open(source, "rb") as f_in:
            with gzip.open(dest, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

    def _cleanup_old_files(self, directory: Path, base_name: str) -> None:
        """
        Clean up old files that exceed the reserved number.
        """
        if self.backup_count <= 0:
            return

        # Find all rotation files
        pattern = f"{base_name}.*"
        log_files = []

        for f in directory.glob(pattern):
            if f.name != Path(self.baseFilename).name:
                log_files.append(f)

        # Sort by modification time
        log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        # Delete excess files
        for old_file in log_files[self.backup_count :]:
            try:
                old_file.unlink()
            except OSError:
                pass


class AsyncHandler(QueueHandler):
    """Asynchronous log processor.

    uses a queue to move log write operations to a background thread to avoid blocking the main thread.
    """

    def __init__(
        self,
        handlers: list[logging.Handler],
        queue_size: int = 10000,
        respect_handler_level: bool = True,
    ) -> None:
        # Create the queue
        self._log_queue: queue.Queue = queue.Queue(maxsize=queue_size)
        super().__init__(self._log_queue)

        # Create the listener
        self._listener = QueueListener(
            self._log_queue,
            *handlers,
            respect_handler_level=respect_handler_level,
        )
        self._listener.start()

        # Clean up when registering and exiting
        atexit.register(self.close)

    def close(self) -> None:
        """
        Close the processor.
        """
        try:
            self._listener.stop()
        except Exception as e:
            logging.getLogger(__name__).debug(t('停止日志监听器失败: {value1}', value1=e))
        super().close()

    def emit(self, record: logging.LogRecord) -> None:
        """
        Send log records to the queue.
        """
        try:
            self.enqueue(record)
        except queue.Full:
            logging.getLogger(__name__).debug(t("日志队列已满，丢弃一条日志"))


