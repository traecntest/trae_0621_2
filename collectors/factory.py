import logging
from typing import List

from collectors.base import CollectedItem, Collector
from collectors.browser_collector import BrowserCollector
from collectors.http_collector import HttpCollector
from collectors.rss_collector import RSSCollector

logger = logging.getLogger(__name__)

_BROWSER_HOSTS = ("bilibili.com", "b23.tv")
_RSS_HINTS = ("/rss", ".rss", "feed", "atom.xml")


def get_collector(source: str) -> Collector:
    """根据来源 URL 选择合适的采集器。

    * B 站等强动态站点 -> :class:`BrowserCollector`
    * RSS / Atom 链接  -> :class:`RSSCollector`
    * 其余站点         -> :class:`HttpCollector`
    """
    url = source.lower()
    if any(h in url for h in _BROWSER_HOSTS):
        return BrowserCollector()
    if any(h in url for h in _RSS_HINTS):
        return RSSCollector()
    return HttpCollector()


def collect(source: str) -> List[CollectedItem]:
    """便捷入口：根据来源自动选择采集器并执行抓取。"""
    collector = get_collector(source)
    if isinstance(collector, BrowserCollector):
        return collector.fetch_with_browser(source)
    return collector.fetch(source)
