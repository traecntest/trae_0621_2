import logging
from typing import List

from collectors.base import CollectedItem, Collector

logger = logging.getLogger(__name__)


class RSSCollector(Collector):
    """RSS / Atom 订阅源采集器。

    复用基类的请求逻辑获取原始 XML，再通过 feedparser 解析，
    避免对官方 API 的依赖同时保证结构化字段稳定。
    """

    name = "rss"

    def parse(self, html: str, base_url: str) -> List[CollectedItem]:
        try:
            import feedparser
        except ImportError:
            logger.error("缺少 feedparser 依赖，无法解析 RSS 源")
            return []
        feed = feedparser.parse(html)
        items: List[CollectedItem] = []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue
            summary = entry.get("summary", "")[:200]
            author = entry.get("author")
            published = entry.get("published") or entry.get("updated")
            content = None
            if entry.get("content"):
                content = entry["content"][0].get("value")
            source = feed.feed.get("title", "RSS")
            items.append(CollectedItem(
                title=title, url=link, source=source, author=author,
                summary=summary, content=content, published_at=published,
            ))
        return items
