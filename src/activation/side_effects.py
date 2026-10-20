"""Activate verification code side effects: clipboard and voice broadcast."""

from __future__ import annotations

from typing import Optional

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


def apply_code_side_effects(code: str, message: Optional[str] = None) -> None:
    """Log clipboard broadcast; not responsible for CLI/GUI copywriting."""
    if not code:
        return
    msg = message or t("请在控制面板输入验证码")
    logger.info(t('激活提示: {value1}', value1=msg))
    logger.info(t('验证码: {value1}', value1=code))

    text = t(".请登录到控制面板添加设备，输入验证码：{code}...", code=" ".join(code))
    try:
        from src.utils.common_utils import handle_verification_code

        handle_verification_code(text)
    except Exception as e:
        logger.debug(t('复制验证码失败: {value1}', value1=e))

    try:
        from src.utils.activation_announcer import announce_activation_code

        announce_activation_code(code, locale="zh-CN")
    except Exception as e:
        logger.debug(t('验证码播报失败: {value1}', value1=e))


def announce_code(code: str) -> None:
    """Only broadcast (used when polling retry)."""
    if not code:
        return
    from src.utils.activation_announcer import announce_activation_code

    announce_activation_code(code, locale="zh-CN")
