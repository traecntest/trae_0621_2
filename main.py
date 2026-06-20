import logging
import sys
import threading
from tkinter import messagebox

from config import APP_TITLE, APP_VERSION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(APP_TITLE)


def main():
    from database.db_manager import DatabaseManager
    from scheduler.task_scheduler import TaskScheduler
    from ui.disclaimer import show_disclaimer_if_first_run
    from ui.main_window import MainWindow
    from ui.notifications import Notifier
    from ui.tray import TrayManager

    db = DatabaseManager()

    if not show_disclaimer_if_first_run():
        logger.warning("用户未同意免责声明，程序退出")
        sys.exit(0)

    notifier = Notifier()
    scheduler = TaskScheduler(db, on_new_content=lambda arts: None,
                              on_fetch_error=lambda s, e: None)
    window = MainWindow(db, scheduler, notifier)

    scheduler.on_new_content = window.handle_new_content
    scheduler.on_fetch_error = window.handle_fetch_error

    def on_close():
        window.minimize_to_tray()

    window.set_close_callback(on_close)

    def on_quit():
        window.root.after(0, window.root.destroy)

    tray = TrayManager(on_show=window.show_from_tray, on_quit=on_quit)
    tray.on_fetch_all = lambda: _fetch_all(scheduler, window)
    tray.start()

    scheduler.start()
    logger.info("%s v%s 启动完成", APP_TITLE, APP_VERSION)

    try:
        window.run()
    finally:
        _cleanup(scheduler, tray, db)


def _fetch_all(scheduler, window):
    def _worker():
        total_added = 0
        total_found = 0
        total_failed = 0
        errors = []
        for topic in scheduler.db.get_all_topics(enabled_only=True):
            stats = scheduler.run_topic_now(topic["id"])
            total_added += stats["items_added"]
            total_found += stats["items_found"]
            total_failed += stats["sources_failed"]
            errors.extend(stats["errors"])
        def _update_ui():
            window._refresh_articles()
            status_msg = (f"批量抓取完成: 找到{total_found}条，入库{total_added}条")
            if total_failed > 0:
                status_msg += f"，失败{total_failed}个来源"
            window.status_var.set(status_msg)
            if errors:
                err_text = "\n".join(errors[:3])
                messagebox.showwarning(
                    "批量抓取有错误",
                    f"共 {len(errors)} 个错误:\n\n{err_text}",
                    parent=window.root,
                )
        window.root.after(0, _update_ui)
    threading.Thread(target=_worker, daemon=True).start()


def _cleanup(scheduler, tray, db):
    try:
        scheduler.shutdown(wait=False)
    except Exception as exc:
        logger.warning("调度器关闭异常: %s", exc)
    try:
        tray.stop()
    except Exception as exc:
        logger.warning("托盘关闭异常: %s", exc)
    try:
        db.close()
    except Exception as exc:
        logger.warning("数据库关闭异常: %s", exc)
    logger.info("程序已退出")


if __name__ == "__main__":
    main()
