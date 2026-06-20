import logging
from typing import List

from config import APP_TITLE, NOTIFY_ON_RELEVANCE

logger = logging.getLogger(__name__)


class Notifier:
    """桌面通知器。

    优先使用 plyer 的跨平台通知；若 plyer 不可用则记录日志降级处理。
    所有通知调用都设计为线程安全，可在调度器线程中直接调用。
    """

    def __init__(self, app_title: str = APP_TITLE):
        self.app_title = app_title
        self._available = self._check_available()

    @staticmethod
    def _check_available() -> bool:
        try:
            from plyer import notification
            return True
        except Exception:
            logger.warning("plyer 不可用，桌面通知将降级为日志输出")
            return False

    def notify_new_content(self, articles: List[dict]):
        if not articles:
            return
        high = [a for a in articles if a.get("relevance_score", 0) >= NOTIFY_ON_RELEVANCE]
        if not high:
            return
        count = len(high)
        best = high[0]
        title = f"[{self.app_title}] 发现 {count} 篇高相关内容"
        message = best.get("title", "")[:80]
        if count > 1:
            message += f" ……等 {count} 篇"
        self._show(title, message)

    def notify(self, title: str, message: str):
        self._show(title, message)

    def _show(self, title: str, message: str):
        if self._available:
            try:
                from plyer import notification
                notification.notify(
                    title=title,
                    message=message,
                    app_name=self.app_title,
                    timeout=8,
                )
                return
            except Exception as exc:
                logger.warning("桌面通知发送失败，降级日志: %s", exc)
        logger.info("通知 | %s | %s", title, message)
