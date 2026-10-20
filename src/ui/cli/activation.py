"""CLI mode device activation process."""
from datetime import datetime

from src.i18n import t
from src.logging import get_logger
from src.ui.shared.activation import BaseActivation

logger = get_logger()


class CliActivation(BaseActivation):
    """CLI mode device activation processor.

    Inherits BaseActivation and only covers the display method of terminal output.
    """

    def __init__(self, activation_service, init_result: dict):
        super().__init__(activation_service, init_result)

    async def run(self) -> bool:
        self._print_header()

        if not self.needs_activation():
            self._log(t("设备已激活，无需进一步操作"))
            self._print_success()
            return True

        self._print_device_info()
        try:
            return await self._core_activate()
        except KeyboardInterrupt:
            self._log(t("\n用户中断激活流程"))
            return False

    # ---- BaseActivation display method ----

    def _show_code(self, data: dict) -> None:
        self._print_activation_info(data)

    def _show_result(self, success: bool) -> None:
        if success:
            self._print_success()
        else:
            self._print_failure()

    def _show_error(self, msg: str) -> None:
        self._log(msg)

    # ---- Terminal display auxiliary method ----

    def _print_header(self):
        print("\n" + "=" * 60)
        print(t('{value0} - 设备激活', value0=t("小智")))
        print("=" * 60)

    def _print_device_info(self):
        """Print device information."""
        serial = self._service.get_serial_number() or "--"
        mac = self._service.get_mac_address() or "--"
        status = self._service.get_activation_status()

        print(t("\n设备信息:"))
        print(t('  序列号: {value1}', value1=serial))
        print(t('  MAC地址: {value1}', value1=mac))

        local = status.get("local_activated", False)
        server = status.get("server_activated", False)
        consistent = status.get("status_consistent", True)

        if not consistent:
            status_text = t("需重新激活") if local and not server else t("已自动修复")
        else:
            status_text = t("已激活") if local else t("未激活")

        print(t('  状态: {value1}', value1=status_text))

    def _print_activation_info(self, data: dict):
        """Print activation information."""
        code = data.get("code", "------")
        message = data.get("message", t("请访问 xiaozhi.me 输入验证码"))

        print("\n" + "-" * 60)
        print(t("激活信息"))
        print("-" * 60)
        print(t('验证码: {value1}', value1=' '.join(code)))
        print(t('说明: {value1}', value1=message))
        print("-" * 60)
        print(t("\n激活步骤:"))
        print(t("  1. 打开浏览器访问 xiaozhi.me"))
        print(t("  2. 登录您的账户"))
        print(t("  3. 选择添加设备"))
        print(t('  4. 输入验证码: {value1}', value1=code))
        print(t("  5. 确认添加设备"))

    def _print_success(self):
        print("\n" + "=" * 60)
        print(t("设备激活成功!"))
        print("=" * 60)
        print(t("设备已成功添加到您的账户"))
        print(t('正在启动{value1}...', value1=t("小智")))
        print("=" * 60 + "\n")

    def _print_failure(self):
        print("\n" + "=" * 60)
        print(t("设备激活失败"))
        print("=" * 60)
        print(t("可能的原因:"))
        print(t("  - 网络连接不稳定"))
        print(t("  - 验证码输入错误或已过期"))
        print(t("  - 服务器暂时不可用"))
        print(t("\n解决方案:"))
        print(t("  - 检查网络连接"))
        print(t("  - 重新运行程序获取新验证码"))
        print(t("  - 确保正确输入验证码"))
        print("=" * 60 + "\n")

    def _log(self, message: str):
        """Print logs with timestamps."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        logger.info(message)
