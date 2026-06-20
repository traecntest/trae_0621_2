import re

from typing import Any

_NOISE_TAGS = ("script", "style", "nav", "footer", "header", "aside",
               "form", "iframe", "noscript", "svg")

_WHITESPACE_RE = re.compile(r"\s+")


def _make_soup(raw_html: str) -> Any:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        import html
        import re as _re
        text = _re.sub(r"<[^>]+>", " ", raw_html)
        return html.unescape(text)
    return BeautifulSoup(raw_html, "lxml")


class ContentCleaner:
    """原始内容清洗器。

    负责剥离 HTML 标签、去除噪声节点、规整空白，
    并从正文中提取标题、发布时间、作者与摘要。
    """

    @staticmethod
    def strip_html(raw_html: str) -> str:
        if not raw_html:
            return ""
        soup = _make_soup(raw_html)
        if isinstance(soup, str):
            return _WHITESPACE_RE.sub(" ", soup).strip()
        for tag in soup(_NOISE_TAGS):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        return _WHITESPACE_RE.sub(" ", text).strip()

    @staticmethod
    def extract_summary(text: str, max_len: int = 200) -> str:
        if not text:
            return ""
        text = _WHITESPACE_RE.sub(" ", text).strip()
        if len(text) <= max_len:
            return text
        return text[:max_len].rsplit(" ", 1)[0] + "..."

    @staticmethod
    def extract_publish_time(soup: Any) -> str:
        for selector in ("time[datetime]", "meta[itemprop='datePublished']",
                         ".date", ".time", ".publish-time", "span[data-time]"):
            tag = soup.select_one(selector)
            if tag:
                return tag.get("datetime") or tag.get("content") or tag.get_text(strip=True)
        return ""

    @staticmethod
    def extract_author(soup: Any) -> str:
        for selector in ("meta[itemprop='author']", ".author-name",
                         ".author", "[rel='author']"):
            tag = soup.select_one(selector)
            if tag:
                return tag.get("content") or tag.get_text(strip=True)
        return ""

    @classmethod
    def clean_item(cls, title: str, summary: str, content: str) -> dict:
        clean_title = _WHITESPACE_RE.sub(" ", title or "").strip()
        clean_summary = cls.extract_summary(summary or content)
        clean_content = cls.strip_html(content) if content else ""
        if not clean_summary and clean_content:
            clean_summary = cls.extract_summary(clean_content)
        return {
            "title": clean_title,
            "summary": clean_summary,
            "content": clean_content,
        }
