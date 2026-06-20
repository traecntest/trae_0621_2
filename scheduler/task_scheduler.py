import logging
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import (DEDUP_HAMMING_DISTANCE, MAX_CONCURRENT_TASKS,
                    MIN_FETCH_INTERVAL_MINUTES, NOTIFY_ON_RELEVANCE,
                    RELEVANCE_THRESHOLD, RELEVANCE_TOP_N_NOTIFY)
from collectors.factory import collect
from database.db_manager import DatabaseManager
from processors.cleaner import ContentCleaner
from processors.relevance import RelevanceScorer
from processors.simhash import Simhash

logger = logging.getLogger(__name__)


class TaskScheduler:
    """基于 APScheduler 的任务调度层。

    每个订阅主题对应一个独立的抓取任务，支持自定义抓取频率。
    系统启动时自动加载全部已启用任务至内存调度器，并通过
    ``last_fetched_at`` 字段实现断点续传，确保重启后不遗漏数据。
    """

    def __init__(self, db: DatabaseManager,
                 on_new_content: Optional[Callable[[List[Dict]], None]] = None):
        self.db = db
        self.on_new_content = on_new_content
        self._scheduler = BackgroundScheduler(
            executors={
                "default": {"type": "threadpool", "max_workers": MAX_CONCURRENT_TASKS},
            },
            job_defaults={"coalesce": True, "max_instances": 1},
        )
        self._semaphore = threading.Semaphore(MAX_CONCURRENT_TASKS)
        self._running = False

    def start(self):
        if self._running:
            return
        self._scheduler.start()
        self._running = True
        self.reload_topics()
        logger.info("任务调度器已启动，共加载 %d 个任务", len(self._scheduler.get_jobs()))

    def shutdown(self, wait: bool = True):
        if self._running:
            self._scheduler.shutdown(wait=wait)
            self._running = False
        logger.info("任务调度器已停止")

    @property
    def running(self) -> bool:
        return self._running

    def reload_topics(self):
        """从数据库重新加载全部已启用主题到调度器。"""
        for job in self._scheduler.get_jobs():
            job.remove()
        for topic in self.db.get_all_topics(enabled_only=True):
            self._add_topic_job(topic)
        logger.info("已重新加载 %d 个订阅任务", len(self._scheduler.get_jobs()))

    def _add_topic_job(self, topic: Dict):
        interval = max(topic["interval_minutes"], MIN_FETCH_INTERVAL_MINUTES)
        job_id = f"topic_{topic['id']}"
        self._scheduler.add_job(
            self._run_topic,
            trigger=IntervalTrigger(minutes=interval),
            id=job_id,
            args=[topic["id"]],
            replace_existing=True,
        )
        logger.debug("注册任务 %s (间隔 %d 分钟)", topic["name"], interval)

    def add_topic(self, topic_id: int):
        topic = self.db.get_topic(topic_id)
        if topic:
            self._add_topic_job(topic)

    def remove_topic(self, topic_id: int):
        job_id = f"topic_{topic_id}"
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

    def update_topic(self, topic_id: int):
        self.remove_topic(topic_id)
        topic = self.db.get_topic(topic_id)
        if topic and topic["enabled"]:
            self._add_topic_job(topic)

    def run_topic_now(self, topic_id: int):
        """手动触发某主题的抓取（用于立即执行按钮）。"""
        self._run_topic(topic_id)

    def _run_topic(self, topic_id: int):
        topic = self.db.get_topic(topic_id)
        if not topic or not topic["enabled"]:
            return
        with self._semaphore:
            logger.info("开始执行主题抓取: %s", topic["name"])
            new_articles: List[Dict] = []
            for source in topic["sources"]:
                try:
                    items = collect(source)
                except Exception as exc:
                    logger.exception("抓取 %s 失败: %s", source, exc)
                    continue
                for item in items:
                    article = self._process_item(item, topic)
                    if article:
                        new_articles.append(article)
            self.db.update_topic_fetched(topic_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            if new_articles and self.on_new_content:
                top = sorted(new_articles, key=lambda a: a["relevance_score"],
                             reverse=True)[:RELEVANCE_TOP_N_NOTIFY]
                high = [a for a in top if a["relevance_score"] >= NOTIFY_ON_RELEVANCE]
                if high:
                    try:
                        self.on_new_content(high)
                    except Exception as exc:
                        logger.warning("通知回调失败: %s", exc)
            logger.info("主题 %s 抓取完成，新增 %d 篇相关文章",
                        topic["name"], len(new_articles))

    def _process_item(self, item, topic: Dict) -> Optional[Dict]:
        cleaned = ContentCleaner.clean_item(item.title, item.summary, item.content)
        if not cleaned["title"]:
            return None
        scorer = RelevanceScorer(topic["keywords"])
        score = scorer.score(cleaned["title"], cleaned["summary"], cleaned["content"])
        if score < RELEVANCE_THRESHOLD:
            logger.debug("过滤低相关文章: %s (得分 %.2f)", cleaned["title"], score)
            return None
        fingerprint = Simhash.from_text(cleaned["title"] + " " + cleaned["summary"])
        simhash_hex = fingerprint.to_hex()
        if self.db.article_exists_by_simhash(simhash_hex, DEDUP_HAMMING_DISTANCE):
            logger.debug("跳过重复文章: %s", cleaned["title"])
            return None
        article = {
            "topic_id": topic["id"],
            "title": cleaned["title"],
            "url": item.url,
            "source": item.source,
            "author": item.author,
            "summary": cleaned["summary"],
            "content": cleaned["content"],
            "published_at": item.published_at,
            "simhash": simhash_hex,
            "relevance_score": round(score, 4),
        }
        new_id = self.db.add_article(article)
        if new_id:
            article["id"] = new_id
            return article
        return None

    def get_job_status(self) -> List[Dict]:
        jobs = self._scheduler.get_jobs()
        status = []
        for job in jobs:
            topic_id = int(job.id.split("_")[1])
            topic = self.db.get_topic(topic_id)
            status.append({
                "topic_id": topic_id,
                "topic_name": topic["name"] if topic else "?",
                "next_run": job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
                if job.next_run_time else None,
                "interval_minutes": topic["interval_minutes"] if topic else 0,
            })
        return status
