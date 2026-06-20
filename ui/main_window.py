import logging
import threading
import webbrowser
from datetime import datetime
from tkinter import (BOTH, END, NORMAL, DISABLED, LEFT, RIGHT, X, Y, BOTTOM, TOP,
                    HORIZONTAL, VERTICAL, StringVar, Toplevel, messagebox, ttk)

from config import APP_TITLE, DEFAULT_FETCH_INTERVAL_MINUTES, MIN_FETCH_INTERVAL_MINUTES

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    "unread": "未读",
    "read": "已读",
    "starred": "收藏",
    "later": "稍后阅读",
}
STATUS_ORDER = ["unread", "later", "starred", "read"]


class TopicEditorDialog(Toplevel):
    """新增 / 编辑订阅主题的弹窗。"""

    def __init__(self, parent, db, topic=None):
        super().__init__(parent)
        self.db = db
        self.topic = topic
        self.result = None
        is_edit = topic is not None
        self.title("编辑主题" if is_edit else "新增主题")
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        self.name_var = StringVar(value=topic["name"] if is_edit else "")
        self.keywords_var = StringVar(
            value="、".join(topic["keywords"]) if is_edit else "")
        self.sources_var = StringVar(
            value="\n".join(topic["sources"]) if is_edit else "")
        self.interval_var = StringVar(
            value=str(topic["interval_minutes"] if is_edit else DEFAULT_FETCH_INTERVAL_MINUTES))
        self.enabled_var = StringVar(
            value="1" if (not is_edit or topic["enabled"]) else "0")

        self._build()
        self.wait_window()

    def _build(self):
        pad = {"padx": 8, "pady": 6}
        ttk.Label(self, text="主题名称:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.name_var, width=40).grid(
            row=0, column=1, columnspan=2, **pad)

        ttk.Label(self, text="关键词 (顿号分隔):").grid(row=1, column=0, sticky="nw", **pad)
        ttk.Entry(self, textvariable=self.keywords_var, width=40).grid(
            row=1, column=1, columnspan=2, **pad)

        ttk.Label(self, text="监控来源 (每行一个URL):").grid(row=2, column=0, sticky="nw", **pad)
        src_text = tk_Text(self, width=42, height=6)
        src_text.grid(row=2, column=1, columnspan=2, **pad)
        src_text.insert("1.0", self.sources_var.get())

        ttk.Label(self, text="抓取频率(分钟):").grid(row=3, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.interval_var, width=10).grid(
            row=3, column=1, sticky="w", **pad)

        ttk.Label(self, text="启用:").grid(row=3, column=2, sticky="w", **pad)
        ttk.Combobox(self, textvariable=self.enabled_var, state="readonly",
                     values=["1", "0"], width=3).grid(row=3, column=3, **pad)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=12)
        ttk.Button(btn_frame, text="保存", command=lambda: self._save(src_text)).pack(side=LEFT, padx=6)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side=LEFT, padx=6)

    def _save(self, src_text):
        name = self.name_var.get().strip()
        keywords_raw = self.keywords_var.get().strip()
        sources_raw = src_text.get("1.0", END).strip()
        if not name:
            messagebox.showwarning("提示", "请填写主题名称", parent=self)
            return
        if not sources_raw:
            messagebox.showwarning("提示", "请至少填写一个监控来源", parent=self)
            return
        try:
            interval = int(self.interval_var.get().strip())
        except ValueError:
            messagebox.showwarning("提示", "抓取频率需为整数", parent=self)
            return
        interval = max(interval, MIN_FETCH_INTERVAL_MINUTES)
        keywords = [k.strip() for k in keywords_raw.replace(",", "、").split("、") if k.strip()]
        sources = [s.strip() for s in sources_raw.splitlines() if s.strip()]
        enabled = self.enabled_var.get() == "1"
        self.result = {
            "name": name, "keywords": keywords, "sources": sources,
            "interval_minutes": interval, "enabled": enabled,
        }
        self.destroy()


def tk_Text(parent, **kw):
    import tkinter as tk
    return tk.Text(parent, **kw)


class MainWindow:
    """三栏式主界面。

    左栏：订阅主题列表（增删改）；
    中栏：内容流（文章卡片，含标题/来源/摘要/时间/相关性）；
    右栏：详情预览（正文展示 + 浏览器跳转 + 状态标记）。
    """

    def __init__(self, db, scheduler, notifier):
        import tkinter as tk
        self.db = db
        self.scheduler = scheduler
        self.notifier = notifier
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1200x720")
        self.root.minsize(960, 600)
        self._current_topic_id = None
        self._current_article_id = None
        self._close_callback = None
        self._build_ui()
        self._refresh_topics()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        self.root.configure(padx=10, pady=10)
        top = ttk.Frame(self.root)
        top.pack(fill=X, pady=(0, 8))
        ttk.Label(top, text=APP_TITLE, font=("Microsoft YaHei UI", 14, "bold")).pack(side=LEFT)
        self.status_var = StringVar(value="就绪")
        ttk.Label(top, textvariable=self.status_var, foreground="#666").pack(side=LEFT, padx=12)
        ttk.Button(top, text="立即抓取", command=self._fetch_current).pack(side=RIGHT, padx=4)
        ttk.Button(top, text="刷新列表", command=self._refresh_articles).pack(side=RIGHT, padx=4)

        paned = ttk.PanedWindow(self.root, orient=HORIZONTAL)
        paned.pack(fill=BOTH, expand=True)

        self._build_left(paned)
        self._build_middle(paned)
        self._build_right(paned)

    def _build_left(self, parent):
        left = ttk.Frame(parent, width=240)
        parent.add(left, weight=1)
        ttk.Label(left, text="订阅主题", font=("Microsoft YaHei UI", 11, "bold")).pack(
            fill=X, pady=(0, 4))
        btns = ttk.Frame(left)
        btns.pack(fill=X, pady=(0, 4))
        ttk.Button(btns, text="+", width=3, command=self._add_topic).pack(side=LEFT, padx=2)
        ttk.Button(btns, text="✎", width=3, command=self._edit_topic).pack(side=LEFT, padx=2)
        ttk.Button(btns, text="−", width=3, command=self._del_topic).pack(side=LEFT, padx=2)

        self.topic_tree = ttk.Treeview(left, columns=("enabled",), show="tree headings",
                                       height=24)
        self.topic_tree.heading("#0", text="主题")
        self.topic_tree.heading("enabled", text="启用")
        self.topic_tree.column("#0", width=160)
        self.topic_tree.column("enabled", width=50, anchor="center")
        self.topic_tree.pack(fill=BOTH, expand=True)
        self.topic_tree.bind("<<TreeviewSelect>>", self._on_topic_select)
        self.topic_tree.bind("<Double-1>", lambda e: self._edit_topic())

    def _build_middle(self, parent):
        mid = ttk.Frame(parent, width=520)
        parent.add(mid, weight=3)
        header = ttk.Frame(mid)
        header.pack(fill=X, pady=(0, 4))
        self.stream_title = StringVar(value="内容流")
        ttk.Label(header, textvariable=self.stream_title,
                  font=("Microsoft YaHei UI", 11, "bold")).pack(side=LEFT)
        self.filter_var = StringVar(value="全部")
        ttk.Combobox(header, textvariable=self.filter_var, state="readonly",
                     values=["全部", "未读", "稍后阅读", "收藏", "已读"],
                     width=10).pack(side=RIGHT, padx=4)

        columns = ("source", "published", "relevance", "status")
        self.article_tree = ttk.Treeview(mid, columns=columns, show="tree headings", height=20)
        self.article_tree.heading("#0", text="标题")
        self.article_tree.heading("source", text="来源")
        self.article_tree.heading("published", text="发布时间")
        self.article_tree.heading("relevance", text="相关性")
        self.article_tree.heading("status", text="状态")
        self.article_tree.column("#0", width=280)
        self.article_tree.column("source", width=80)
        self.article_tree.column("published", width=130)
        self.article_tree.column("relevance", width=60, anchor="center")
        self.article_tree.column("status", width=70, anchor="center")
        vsb = ttk.Scrollbar(mid, orient=VERTICAL, command=self.article_tree.yview)
        self.article_tree.configure(yscrollcommand=vsb.set)
        self.article_tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)
        self.article_tree.bind("<<TreeviewSelect>>", self._on_article_select)

    def _build_right(self, parent):
        right = ttk.Frame(parent, width=420)
        parent.add(right, weight=2)
        ttk.Label(right, text="详情预览", font=("Microsoft YaHei UI", 11, "bold")).pack(
            fill=X, pady=(0, 4))
        actions = ttk.Frame(right)
        actions.pack(fill=X, pady=(0, 4))
        ttk.Button(actions, text="已读", command=lambda: self._set_status("read")).pack(side=LEFT, padx=2)
        ttk.Button(actions, text="收藏", command=lambda: self._toggle_star()).pack(side=LEFT, padx=2)
        ttk.Button(actions, text="稍后阅读", command=lambda: self._set_status("later")).pack(side=LEFT, padx=2)
        ttk.Button(actions, text="浏览器打开", command=self._open_in_browser).pack(side=RIGHT, padx=2)

        self.detail_text = tk_Text(right, wrap="word", state=DISABLED)
        dsb = ttk.Scrollbar(right, orient=VERTICAL, command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=dsb.set)
        self.detail_text.pack(side=LEFT, fill=BOTH, expand=True)
        dsb.pack(side=RIGHT, fill=Y)

    def _refresh_topics(self):
        for item in self.topic_tree.get_children():
            self.topic_tree.delete(item)
        topics = self.db.get_all_topics()
        if not topics:
            self.topic_tree.insert("", END, text="（暂无主题，点击 + 新增）", values=("",))
            return
        for t in topics:
            self.topic_tree.insert("", END, iid=str(t["id"]),
                                   text=t["name"],
                                   values=("是" if t["enabled"] else "否",))

    def _on_topic_select(self, _event=None):
        sel = self.topic_tree.selection()
        if not sel:
            return
        try:
            self._current_topic_id = int(sel[0])
        except ValueError:
            self._current_topic_id = None
            return
        self._refresh_articles()

    def _refresh_articles(self):
        for item in self.article_tree.get_children():
            self.article_tree.delete(item)
        filter_map = {"未读": "unread", "稍后阅读": "later", "收藏": "starred", "已读": "read"}
        status = filter_map.get(self.filter_var.get())
        topic_id = self._current_topic_id if self._current_topic_id else None
        name = "全部内容"
        if topic_id:
            topic = self.db.get_topic(topic_id)
            name = f"{topic['name']} 的内容流" if topic else "内容流"
        self.stream_title.set(name)

        articles = self.db.get_articles(topic_id=topic_id, status=status, limit=300)
        for a in articles:
            rel = f"{a['relevance_score']:.2f}"
            self.article_tree.insert(
                "", END, iid=str(a["id"]), text=a["title"],
                values=(a["source"], a.get("published_at") or a.get("fetched_at", ""),
                        rel, STATUS_LABELS.get(a["status"], a["status"])))
        self.status_var.set(f"共 {len(articles)} 篇")

    def _on_article_select(self, _event=None):
        sel = self.article_tree.selection()
        if not sel:
            return
        self._current_article_id = int(sel[0])
        article = self.db.get_article(self._current_article_id)
        if not article:
            return
        self._show_detail(article)
        if article["status"] == "unread":
            self.db.set_article_status(self._current_article_id, "read")
            self.db.record_action(self._current_article_id, "read")
            self._refresh_articles()

    def _show_detail(self, article):
        self.detail_text.configure(state=NORMAL)
        self.detail_text.delete("1.0", END)
        lines = [
            article["title"],
            f"来源: {article['source']}    作者: {article.get('author') or '未知'}",
            f"发布时间: {article.get('published_at') or '未知'}    相关性: {article['relevance_score']:.2f}",
            f"链接: {article['url']}",
            "-" * 60,
            article.get("summary") or "",
            "",
            article.get("content") or "（未抓取正文，点击「浏览器打开」查看原文）",
        ]
        self.detail_text.insert("1.0", "\n".join(lines))
        self.detail_text.configure(state=DISABLED)

    def _set_status(self, status):
        if not self._current_article_id:
            return
        self.db.set_article_status(self._current_article_id, status)
        self.db.record_action(self._current_article_id, status)
        self._refresh_articles()

    def _toggle_star(self):
        if not self._current_article_id:
            return
        article = self.db.get_article(self._current_article_id)
        if not article:
            return
        if article["status"] == "starred":
            self.db.set_article_status(self._current_article_id, "read")
            self.db.record_action(self._current_article_id, "unstarred")
        else:
            self.db.set_article_status(self._current_article_id, "starred")
            self.db.record_action(self._current_article_id, "starred")
        self._refresh_articles()

    def _open_in_browser(self):
        if not self._current_article_id:
            messagebox.showinfo("提示", "请先选择一篇文章", parent=self.root)
            return
        article = self.db.get_article(self._current_article_id)
        if not article:
            messagebox.showwarning("提示", "未找到该文章", parent=self.root)
            return
        if not article.get("url"):
            messagebox.showwarning("提示", "该文章没有可用链接", parent=self.root)
            return
        try:
            webbrowser.open(article["url"])
            self.status_var.set("已在浏览器中打开")
        except Exception as exc:
            messagebox.showerror("错误", f"打开浏览器失败: {exc}", parent=self.root)

    def _add_topic(self):
        dlg = TopicEditorDialog(self.root, self.db)
        if dlg.result:
            r = dlg.result
            topic_id = self.db.add_topic(r["name"], r["keywords"], r["sources"],
                                         r["interval_minutes"], r["enabled"])
            self.scheduler.add_topic(topic_id)
            self._refresh_topics()
            self.status_var.set(f"已新增主题: {r['name']}")

    def _edit_topic(self):
        if not self._current_topic_id:
            messagebox.showinfo("提示", "请先选择一个主题", parent=self.root)
            return
        topic = self.db.get_topic(self._current_topic_id)
        if not topic:
            return
        dlg = TopicEditorDialog(self.root, self.db, topic=topic)
        if dlg.result:
            r = dlg.result
            self.db.update_topic(self._current_topic_id, name=r["name"], keywords=r["keywords"],
                                 sources=r["sources"], interval_minutes=r["interval_minutes"],
                                 enabled=r["enabled"])
            self.scheduler.update_topic(self._current_topic_id)
            self._refresh_topics()
            self.status_var.set(f"已更新主题: {r['name']}")

    def _del_topic(self):
        if not self._current_topic_id:
            messagebox.showinfo("提示", "请先选择一个主题", parent=self.root)
            return
        if messagebox.askyesno("确认", "确定删除该主题及其所有文章？", parent=self.root):
            self.db.delete_topic(self._current_topic_id)
            self.scheduler.remove_topic(self._current_topic_id)
            self._current_topic_id = None
            self._refresh_topics()
            self._refresh_articles()

    def _fetch_current(self):
        if not self._current_topic_id:
            messagebox.showinfo("提示", "请先选择一个主题", parent=self.root)
            return
        self.status_var.set("正在抓取…")
        threading.Thread(target=self._fetch_in_background, daemon=True).start()

    def _fetch_in_background(self):
        stats = None
        fetch_exception = None
        try:
            stats = self.scheduler.run_topic_now(self._current_topic_id)
        except Exception as exc:
            fetch_exception = exc
            logger.exception("抓取任务异常")
        finally:
            self.root.after(0, self._after_fetch, stats, fetch_exception)

    def _after_fetch(self, stats, fetch_exception=None):
        self._refresh_articles()
        if fetch_exception:
            err_text = str(fetch_exception)
            self.status_var.set(f"抓取失败: {err_text[:50]}")
            messagebox.showerror(
                "抓取失败",
                f"抓取过程中发生未预期的错误:\n\n{err_text}\n\n"
                "请检查网络连接或查看日志了解详情。",
                parent=self.root,
            )
            return
        if not stats:
            self.status_var.set("抓取完成")
            return
        topic_name = stats["topic_name"]
        found = stats["items_found"]
        added = stats["items_added"]
        filtered = stats["items_filtered"]
        duplicate = stats["items_duplicate"]
        failed = stats["sources_failed"]
        total = stats["sources_total"]
        errors = stats.get("errors", [])
        status_msg = (f"抓取完成: 「{topic_name}」 找到{found}条，"
                      f"入库{added}条，过滤{filtered}条，去重{duplicate}条")
        if failed > 0:
            status_msg += f"，来源失败{failed}/{total}"
        self.status_var.set(status_msg)
        if errors and added == 0 and found == 0:
            err_text = "\n".join(errors[:5])
            if len(errors) > 5:
                err_text += f"\n... 共 {len(errors)} 条错误"
            messagebox.showwarning(
                "抓取完成但无内容",
                f"未获取到任何文章。\n\n错误详情:\n{err_text}\n\n"
                "可能的原因:\n1. 来源站点无法访问或解析失败\n2. 关键词设置与内容不匹配\n3. 网络连接问题或被反爬拦截",
                parent=self.root,
            )
        elif added == 0 and found > 0:
            messagebox.showinfo(
                "抓取完成但已过滤",
                f"共解析到 {found} 条内容，但全部未通过相关性筛选。\n"
                f"（被过滤 {filtered} 条，重复 {duplicate} 条）\n\n"
                "建议：调整关键词使其与来源内容更匹配",
                parent=self.root,
            )
        elif errors:
            err_text = "\n".join(errors[:3])
            if len(errors) > 3:
                err_text += f"\n... 共 {len(errors)} 条错误"
            messagebox.showwarning(
                "抓取有部分错误",
                f"成功入库 {added} 篇，但有 {len(errors)} 个错误:\n\n{err_text}",
                parent=self.root,
            )
        elif added == 0 and found == 0 and not errors:
            messagebox.showinfo(
                "抓取完成但无内容",
                f"未解析到任何内容。\n\n"
                "可能的原因:\n1. 来源站点页面结构已变化\n2. 来源站点需要浏览器渲染（B站等）\n3. 来源页面为空",
                parent=self.root,
            )

    def handle_fetch_error(self, source: str, error: str):
        """线程安全的「抓取错误」入口，由调度器回调。"""
        self.root.after(0, self._on_fetch_error, source, error)

    def _on_fetch_error(self, source: str, error: str):
        logger.warning("抓取来源失败: %s - %s", source, error)
        self.status_var.set(f"来源抓取失败: {source[:40]}")

    def handle_new_content(self, articles):
        """线程安全的「新内容到达」入口，由调度器回调。"""
        self.root.after(0, self._on_new_content_arrived, articles)

    def _on_new_content_arrived(self, articles):
        self.notifier.notify_new_content(articles)
        self._refresh_articles()
        self.status_var.set(f"新到 {len(articles)} 篇相关内容")

    def minimize_to_tray(self):
        self.root.withdraw()

    def show_from_tray(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _on_close(self):
        self._close_callback() if self._close_callback else self.root.destroy()

    def set_close_callback(self, callback):
        self._close_callback = callback

    def run(self):
        self.root.mainloop()
