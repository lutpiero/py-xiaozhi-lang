"""
General tool function collection module.

includes general tool functions such as browser operation, clipboard, and verification code extraction.
"""
import re
import webbrowser
from typing import Optional

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


def open_url(url: str) -> bool:
    """Open web link."""
    try:
        success = webbrowser.open(url)
        if success:
            logger.info(t('已成功打开网页: {value1}', value1=url))
        else:
            logger.warning(t('无法打开网页: {value1}', value1=url))
        return success
    except Exception as e:
        logger.error(t('打开网页时出错: {value1}', value1=e), exc_info=True)
        return False


def copy_to_clipboard(text: str) -> bool:
    """Copy text to clipboard."""
    try:
        import pyperclip

        pyperclip.copy(text)
        logger.info(t('文本 "{value1}" 已复制到剪贴板', value1=text))
        return True
    except ImportError:
        logger.warning(t("未安装pyperclip模块，无法复制到剪贴板"))
        return False
    except Exception as e:
        logger.error(t('复制到剪贴板时出错: {value1}', value1=e), exc_info=True)
        return False


def extract_verification_code(text: str) -> Optional[str]:
    """extracts verification codes from text."""
    try:
        # Activation-related keyword list
        activation_keywords = [
            "登录",
            "控制面板",
            "激活",
            "验证码",
            "绑定设备",
            "添加设备",
            "输入验证码",
            "输入",
            "面板",
            "xiaozhi.me",
            "激活码",
        ]

        # Check whether the text contains activation-related keywords
        has_activation_keyword = any(keyword in text for keyword in activation_keywords)

        if not has_activation_keyword:
            logger.debug(t('文本不包含激活关键词，跳过验证码提取: {value1}', value1=text))
            return None

        # More accurate verification code matching pattern Formula
        patterns = [
            r"验证码[：:]\s*(\d{6})",
            r"输入验证码[：:]\s*(\d{6})",
            r"输入\s*(\d{6})",
            r"验证码\s*(\d{6})",
            r"激活码[：:]\s*(\d{6})",
            r"(\d{6})[，,。.]",
            r"[，,。.]\s*(\d{6})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                code = match.group(1)
                logger.info(t('已从文本中提取验证码: {value1}', value1=code))
                return code

        # General pattern matching
        match = re.search(r"((?:\d\s*){6,})", text)
        if match:
            code = "".join(match.group(1).split())
            if len(code) == 6 and code.isdigit():
                logger.info(t('已从文本中提取验证码（通用模式）: {value1}', value1=code))
                return code

        logger.warning(t('未能从文本中找到验证码: {value1}', value1=text))
        return None
    except Exception as e:
        logger.error(t('提取验证码时出错: {value1}', value1=e), exc_info=True)
        return None


def handle_verification_code(text: str) -> None:
    """Process verification code: extract and copy to clipboard."""
    code = extract_verification_code(text)
    if code:
        copy_to_clipboard(code)
