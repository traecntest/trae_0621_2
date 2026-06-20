import logging
import re
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collectors.base import CollectedItem, Collector

logger = logging.getLogger(__name__)


class HttpCollector(Collector):
    """基于 Requests + BeautifulSoup 的通用 HTML 采集器。

    针对知乎、CSDN、简书等站点内置了平台解析规则；未匹配平台时
    回退到通用解析策略（优先提取 ``<article>`` / 列表链接）。
    """

    name = "http"

    PLATFORM_RULES = {
        "zhihu.com": "_parse_zhihu",
        "csdn.net": "_parse_csdn",
        "jianshu.com": "_parse_jianshu",
    }

    def parse(self, html: str, base_url: str) -> List[CollectedItem]:
        soup = BeautifulSoup(html, "lxml")
        for host, method_name in self.PLATFORM_RULES.items():
            if host in base_url:
                return getattr(self, method_name)(soup, base_url)
        return self._parse_generic(soup, base_url)

    def _parse_zhihu(self, soup: BeautifulSoup, base_url: str) -> List[CollectedItem]:
        items: List[CollectedItem] = []
        cards = soup.select("div.Card, div.List-item, div.ContentItem")
        for card in cards:
            title_tag = card.select_one("h2 a, .ContentItem-title a, a.ContentItem-title")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            link = title_tag.get("href", "")
            if link.startswith("/"):
                link = urljoin("https://www.zhihu.com", link)
            author_tag = card.select_one(".AuthorInfo-name, meta[itemprop='name']")
            author = author_tag.get_text(strip=True) if author_tag else None
            excerpt_tag = card.select_one(".RichContent-inner, .CopyrightRichText-richText")
            summary = excerpt_tag.get_text(" ", strip=True)[:200] if excerpt_tag else None
            if title and link:
                items.append(CollectedItem(
                    title=title, url=link, source="知乎", author=author, summary=summary,
                ))
        return items

    def _parse_csdn(self, soup: BeautifulSoup, base_url: str) -> List[CollectedItem]:
        items: List[CollectedItem] = []
        articles = soup.select("div.article-item-box, div.blog-list-box, .content-list .item")
        for art in articles:
            link_tag = art.select_one("h4 a, a.blog-list-title, a.title")
            if not link_tag:
                continue
            title = link_tag.get_text(strip=True)
            link = link_tag.get("href", "")
            date_tag = art.select_one(".date, .blog_list_remark, span.time")
            published = date_tag.get_text(strip=True) if date_tag else None
            summary_tag = art.select_one(".blog-list-content, p.content")
            summary = summary_tag.get_text(" ", strip=True)[:200] if summary_tag else None
            if title and link:
                items.append(CollectedItem(
                    title=title, url=link, source="CSDN",
                    summary=summary, published_at=published,
                ))
        return items

    def _parse_jianshu(self, soup: BeautifulSoup, base_url: str) -> List[CollectedItem]:
        items: List[CollectedItem] = []
        cards = soup.select("li.have-img, div.content, section.note-list li")
        for card in cards:
            link_tag = card.select_one("a.title, a.name")
            if not link_tag:
                continue
            title = link_tag.get_text(strip=True)
            link = link_tag.get("href", "")
            if link.startswith("/"):
                link = urljoin("https://www.jianshu.com", link)
            author_tag = card.select_one(".author-name, a.nickname")
            author = author_tag.get_text(strip=True) if author_tag else None
            abstract_tag = card.select_one(".abstract, p.content")
            summary = abstract_tag.get_text(" ", strip=True)[:200] if abstract_tag else None
            if title and link:
                items.append(CollectedItem(
                    title=title, url=link, source="简书", author=author, summary=summary,
                ))
        return items

    def _parse_generic(self, soup: BeautifulSoup, base_url: str) -> List[CollectedItem]:
        items: List[CollectedItem] = []
        seen = set()

        article_tags = soup.select("article") or soup.select("[role='article']")
        if article_tags:
            for art in article_tags:
                link_tag = art.select_one("a[href]")
                title_tag = art.select_one("h1, h2, h3, .title")
                title = (title_tag or link_tag).get_text(strip=True) if (title_tag or link_tag) else ""
                link = link_tag.get("href", "") if link_tag else ""
                if link:
                    link = urljoin(base_url, link)
                if title and link and link not in seen:
                    seen.add(link)
                    summary = art.get_text(" ", strip=True)[:200]
                    items.append(CollectedItem(title=title, url=link,
                                               source=self._domain(base_url), summary=summary))
            if items:
                return items

        for a in soup.select("a[href]"):
            link = urljoin(base_url, a.get("href", ""))
            if not link.startswith("http"):
                continue
            if "#" in link or link.endswith((".jpg", ".png", ".css", ".js")):
                continue
            title = a.get_text(strip=True)
            if len(title) < 6 or link in seen:
                continue
            seen.add(link)
            items.append(CollectedItem(title=title, url=link, source=self._domain(base_url)))
        return items

    @staticmethod
    def _domain(url: str) -> str:
        m = re.match(r"https?://([^/]+)/?", url)
        return m.group(1) if m else url

    def fetch_detail(self, url: str) -> CollectedItem:
        """抓取单篇文章正文，用于详情预览。"""
        resp = self._request(url)
        self._polite_delay()
        if resp is None:
            return CollectedItem(title="", url=url, source=self._domain(url))
        soup = BeautifulSoup(resp.text, "lxml")
        title = soup.title.get_text(strip=True) if soup.title else ""
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        content_tag = soup.select_one("article") or soup.body or soup
        text = content_tag.get_text("\n", strip=True)
        return CollectedItem(
            title=title, url=url, source=self._domain(url),
            content=text, summary=text[:200],
        )
