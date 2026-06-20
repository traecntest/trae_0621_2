import logging
import threading
from typing import Callable, Optional

from config import APP_TITLE

logger = logging.getLogger(__name__)


class TrayManager:
    """系统托盘管理器。

    基于 pystray 实现常驻后台托盘图标，支持最小化到托盘、
    恢复窗口与退出程序。当 pystray 不可用时优雅降级，
    不影响主程序运行。
    """

    def __init__(self, on_show: Callable, on_quit: Callable,
                 app_title: str = APP_TITLE):
        self.on_show = on_show
        self.on_quit = on_quit
        self.app_title = app_title
        self._icon = None
        self._thread: Optional[threading.Thread] = None

    def _build_icon_image(self):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (64, 64), color=(30, 136, 229))
        draw = ImageDraw.Draw(img)
        draw.rectangle((12, 16, 52, 22), fill=(255, 255, 255))
        draw.rectangle((12, 26, 44, 32), fill=(200, 230, 255))
        draw.rectangle((12, 36, 48, 42), fill=(200, 230, 255))
        return img

    def _build_icon(self):
        from pystray import Icon, Menu, MenuItem
        menu = Menu(
            MenuItem("显示主窗口", self._on_show, default=True),
            MenuItem("立即抓取全部", self._on_fetch_all),
            Menu.SUBMENU_SEPARATOR,
            MenuItem("退出", self._on_quit),
        )
        return Icon(self.app_title, self._build_icon_image(), self.app_title, menu)

    def _on_show(self, icon=None, item=None):
        try:
            self.on_show()
        except Exception as exc:
            logger.exception("显示窗口失败: %s", exc)

    def _on_fetch_all(self, icon=None, item=None):
        try:
            if hasattr(self, "on_fetch_all") and self.on_fetch_all:
                self.on_fetch_all()
        except Exception as exc:
            logger.exception("触发抓取失败: %s", exc)

    def _on_quit(self, icon=None, item=None):
        try:
            if self._icon:
                self._icon.stop()
        finally:
            self.on_quit()

    def start(self):
        try:
            self._icon = self._build_icon()
        except Exception as exc:
            logger.warning("托盘图标初始化失败，将以无托盘模式运行: %s", exc)
            return
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        logger.info("系统托盘已启动")

    def stop(self):
        if self._icon:
            self._icon.stop()
        logger.info("系统托盘已停止")
