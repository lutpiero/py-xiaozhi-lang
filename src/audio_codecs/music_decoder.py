import asyncio
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

from src.constants.constants import AudioConfig
from src.i18n import t
from src.logging import get_logger
from src.utils.resource_finder import get_ffmpeg_path, get_ffprobe_path

logger = get_logger()

_SUBPROCESS_KW = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)

# The local path or http(s) stream
AudioSource = str | Path


def is_http_url(source: AudioSource) -> bool:
    text = str(source).strip()
    return text.startswith("http://") or text.startswith("https://")


def _source_label(source: AudioSource) -> str:
    if is_http_url(source):
        host = urlparse(str(source)).hostname or "http"
        return f"stream:{host}"
    path = Path(source)
    return path.name


def _ffmpeg_header_args(headers: Mapping[str, str] | None) -> list[str]:
    """is assigned to ffmpeg's -headers / -user_agent (commonly used for HTTP sources)."""
    if not headers:
        return []
    args: list[str] = []
    ua = None
    lines: list[str] = []
    for key, value in headers.items():
        if not value:
            continue
        if key.lower() == "user-agent":
            ua = str(value)
            continue
        lines.append(f"{key}: {value}")
    if lines:
        blob = "".join(f"{line}\r\n" for line in lines)
        args.extend(["-headers", blob])
    if ua:
        args.extend(["-user_agent", ua])
    return args


class MusicDecoder:
    """is only responsible for decoding the sound source into PCM; cache prefetching does not go here (to avoid being tied to the playback progress)."""

    @staticmethod
    async def get_duration(
        source: AudioSource,
        headers: Mapping[str, str] | None = None,
    ) -> float:
        """ffprobe gets the duration; the source can be a local file or http(s) URL."""
        try:
            ffprobe = get_ffprobe_path()
            try:
                check = await asyncio.create_subprocess_exec(
                    ffprobe,
                    "-version",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **_SUBPROCESS_KW,
                )
                await check.wait()
            except FileNotFoundError:
                logger.warning(
                    t('ffprobe 不可用（未找到内置 libs/ffmpeg 且系统 PATH 无 ffprobe），无法获取音频时长。尝试路径: {value1}', value1=ffprobe)
                )
                return 0
            except OSError as e:
                logger.warning(t('ffprobe 启动失败: {value1}: {value3}', value1=ffprobe, value3=e), exc_info=True)
                return 0

            cmd = [ffprobe, "-v", "error"]
            if is_http_url(source):
                cmd.extend(_ffmpeg_header_args(headers))
            cmd.extend(
                [
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(source),
                ]
            )

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_SUBPROCESS_KW
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                duration_str = stdout.decode("utf-8").strip()
                duration = float(duration_str)
                logger.debug(t('解析音频时长: {value1:.2f}秒 ({value3})', value1=duration, value3=_source_label(source)))
                return duration
            else:
                error_msg = stderr.decode("utf-8", errors="ignore")
                logger.warning(t('ffprobe 获取时长失败: {value1}', value1=error_msg))
                return 0

        except Exception as e:
            logger.warning(t('解析音频时长失败: {value1}', value1=e), exc_info=True)
            return 0

    def __init__(self, sample_rate: int = 24000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._process: subprocess.Process | None = None
        self._decode_task: asyncio.Task | None = None
        self._stopped = False

    async def start_decode(
        self,
        source: AudioSource,
        output_queue: asyncio.Queue,
        start_position: float = 0.0,
        headers: Mapping[str, str] | None = None,
        cache_path: Path | None = None,
    ) -> bool:
        """starts decoding. source is local path or http(s).

        cache_path is obsolete and ignored: the cache is copied in the background according to the network speed and is not tied to the playback progress.
        """
        _ = cache_path
        http = is_http_url(source)
        if not http:
            path = Path(source)
            if not path.exists():
                logger.error(t('音频文件不存在: {value1}', value1=path))
                return False
            source = path

        self._stopped = False

        try:
            ffmpeg = get_ffmpeg_path()
            try:
                result = await asyncio.create_subprocess_exec(
                    ffmpeg,
                    "-version",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **_SUBPROCESS_KW,
                )
                await result.wait()
                if result.returncode not in (0, None):
                    logger.error(
                        t('FFmpeg 无法启动（退出码 {value1}）: {value3}。安装包应内置可移植二进制；若仍失败请反馈版本与平台。源码运行请执行 ./scripts/bundle_ffmpeg.sh 或安装系统 ffmpeg', value1=result.returncode, value3=ffmpeg)
                    )
                    return False
            except FileNotFoundError:
                logger.error(
                    t('FFmpeg 不可用：未找到内置 libs/ffmpeg/<plat>/<arch>/ffmpeg，且系统 PATH 中也没有。尝试路径: {value1}。安装包用户无需单独安装系统 FFmpeg；若使用安装包仍失败，请重新下载完整安装包。源码运行请安装 ffmpeg 或执行 ./scripts/bundle_ffmpeg.sh', value1=ffmpeg)
                )
                return False
            except OSError as e:
                logger.error(
                    t('FFmpeg 启动失败（可能缺少动态库）: {value1}: {value3}', value1=ffmpeg, value3=e),
                    exc_info=True,
                )
                return False

            cmd = [ffmpeg]

            if http:
                cmd.extend(
                    [
                        "-reconnect",
                        "1",
                        "-reconnect_streamed",
                        "1",
                        "-reconnect_delay_max",
                        "5",
                    ]
                )
                cmd.extend(_ffmpeg_header_args(headers))

            if start_position > 0.1:
                cmd.extend(["-ss", f"{start_position:.3f}"])

            cmd.extend(
                [
                    "-i",
                    str(source),
                    "-f",
                    "s16le",
                    "-ar",
                    str(self.sample_rate),
                    "-ac",
                    str(self.channels),
                    "-loglevel",
                    "error",
                    "-",
                ]
            )

            self._process = await asyncio.create_subprocess_exec(
                *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_SUBPROCESS_KW
            )

            self._decode_task = asyncio.create_task(self._read_pcm_stream(output_queue))

            position_info = f" from {start_position:.1f}s" if start_position > 0 else ""
            mode = t("流式") if http else t("文件")
            logger.info(
                t('开始解码音频({value1}): {value3}{value4} [{value6}Hz, {value8}ch]', value1=mode, value3=_source_label(source), value4=position_info, value6=self.sample_rate, value8=self.channels)
            )
            return True

        except Exception as e:
            logger.error(t('启动音频解码失败: {value1}', value1=e), exc_info=True)
            return False

    async def _read_pcm_stream(self, output_queue: asyncio.Queue):
        frame_duration_ms = AudioConfig.FRAME_DURATION
        frame_size_samples = int(self.sample_rate * (frame_duration_ms / 1000))
        frame_size_bytes = frame_size_samples * 2 * self.channels
        logger.info(
            t('解码器参数: 帧大小={value1}样本, {value3}字节, {value5}ms', value1=frame_size_samples, value3=frame_size_bytes, value5=frame_duration_ms)
        )

        eof_reached = False
        frame_count = 0

        try:
            while not self._stopped:
                chunk = await self._process.stdout.read(frame_size_bytes)

                if not chunk:
                    duration_decoded = frame_count * frame_duration_ms / 1000
                    logger.info(
                        t('音频解码完成，共 {value1} 帧，时长约 {value3:.1f}秒', value1=frame_count, value3=duration_decoded)
                    )

                    if self._process:
                        try:
                            await asyncio.wait_for(self._process.wait(), timeout=2.0)
                        except (asyncio.TimeoutError, Exception):
                            pass
                        try:
                            stderr_output = await self._process.stderr.read()
                            if stderr_output:
                                err = stderr_output.decode("utf-8", errors="ignore")
                                if err.strip():
                                    logger.warning(f"FFmpeg: {err.strip()[:300]}")
                        except Exception as e:
                            logger.debug(t('读取 FFmpeg stderr 失败: {value1}', value1=e))

                    eof_reached = True
                    break

                frame_count += 1

                audio_array_int16 = np.frombuffer(chunk, dtype=np.int16)
                audio_array = audio_array_int16.astype(np.float32) / 32768.0

                if self.channels > 1:
                    audio_array = audio_array.reshape(-1, self.channels)

                # The beat is completely determined by the downstream backpressure: if the queue is full, it will wait at the put
                # (AudioCodec.write_pcm_direct Release according to buffer water level).
                # no longer uses the "wall clock-start time" speed limit - the wall clock will still run during the pause,
                # After recovery, it will misjudge that it is lagging behind and fill the data at full speed, bursting the playback queue.
                await output_queue.put(audio_array)

        except asyncio.CancelledError:
            logger.debug(t("解码任务被取消"))
        except Exception as e:
            logger.error(t('读取 PCM 流失败: {value1}', value1=e), exc_info=True)
        finally:
            if eof_reached:
                try:
                    await output_queue.put(None)
                except Exception as e:
                    logger.debug(t('发送 EOF 信号失败: {value1}', value1=e))

    async def stop(self):
        if self._stopped:
            return

        self._stopped = True
        logger.debug(t("停止音频解码器"))

        if self._decode_task and not self._decode_task.done():
            self._decode_task.cancel()
            try:
                await self._decode_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(t('解码任务异常: {value1}', value1=e), exc_info=True)

        proc = self._process
        self._process = None
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception as e:
                    logger.debug(t('强制结束 FFmpeg 失败: {value1}', value1=e))
            except ProcessLookupError:
                pass
            except Exception as e:
                if str(e).strip():
                    logger.debug(t('结束 FFmpeg 进程: {value1}', value1=e))

    def is_running(self) -> bool:
        return (
            not self._stopped
            and self._process is not None
            and self._process.returncode is None
        )

    async def wait_completion(self):
        if self._decode_task and not self._decode_task.done():
            try:
                await self._decode_task
            except Exception as e:
                logger.error(t('等待解码完成失败: {value1}', value1=e), exc_info=True)
