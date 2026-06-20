import logging
from typing import List

from bs4 import BeautifulSoup

from collectors.base import CollectedItem, Collector

logger = logging.getLogger(__name__)


class BrowserCollector(Collector):
    """针对动态渲染站点（如 B 站）的浏览器采集器。

    基于 Playwright 进行无头浏览器抓取；当 Playwright 未安装时
    自动降级为基类的 HTTP 请求，保证系统不会因缺少浏览器内核而崩溃。
    """

    name = "browser"

    DYNAMIC_HOSTS = ("bilibili.com", "b站")

    def parse(self, html: str, base_url: str) -> List[CollectedItem]:
        soup = BeautifulSoup(html, "lxml")
        if "bilibili.com" in base_url:
            return self._parse_bilibili(soup, base_url)
        return self._parse_dynamic_generic(soup, base_url)

    def _parse_bilibili(self, soup: BeautifulSoup, base_url: str) -> List[CollectedItem]:
        items: List[CollectedItem] = []
        cards = soup.select(
            "div.video-card, div.video-item, li.video-item, .bili-video-card"
        )
        for card in cards:
            link_tag = card.select_one("a[href*='/video/'], a.title")
            title_tag = card.select_one(".title, p.title, a[title]")
            title = ""
            if title_tag:
                title = title_tag.get("title") or title_tag.get_text(strip=True)
            elif link_tag:
                title = link_tag.get("title") or link_tag.get_text(strip=True)
            link = ""
            if link_tag:
                link = link_tag.get("href", "")
                if link.startswith("//"):
                    link = "https:" + link
            up_tag = card.select_one(".up-name, .author, a.up")
            author = up_tag.get_text(strip=True) if up_tag else None
            if title and link:
                items.append(CollectedItem(
                    title=title, url=link, source="B站", author=author,
                ))
        return items

    def _parse_dynamic_generic(self, soup: BeautifulSoup, base_url: str) -> List[CollectedItem]:
        items: List[CollectedItem] = []
        for a in soup.select("a[href]"):
            link = a.get("href", "")
            title = a.get_text(strip=True)
            if len(title) >= 6 and link:
                items.append(CollectedItem(title=title, url=link, source="browser"))
        return items

    def fetch_with_browser(self, url: str, wait_selector: str = None,
                           wait_ms: int = 3000) -> List[CollectedItem]:
        """使用 Playwright 无头浏览器渲染后抓取。

        若 Playwright 不可用，则降级为普通 HTTP 抓取。
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright 未安装，降级为 HTTP 抓取 %s", url)
            return self.fetch(url)

        logger.info("[browser] 启动浏览器抓取 %s", url)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
                if wait_selector:
                    page.wait_for_selector(wait_selector, timeout=wait_ms)
                else:
                    page.wait_for_timeout(wait_ms)
                html = page.content()
                browser.close()
                self._polite_delay()
                return self.parse(html, url)
        except Exception as exc:
            logger.exception("[browser] 浏览器抓取失败: %s", exc)
            return []
