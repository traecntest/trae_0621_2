import abc
import logging
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import REQUEST_DELAY_RANGE, REQUEST_RETRY_COUNT, REQUEST_TIMEOUT
from collectors.headers import random_headers
from collectors.proxy_pool import proxy_pool

logger = logging.getLogger(__name__)


@dataclass
class CollectedItem:
    title: str
    url: str
    source: str
    author: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    published_at: Optional[str] = None
    extra: dict = field(default_factory=dict)


class Collector(abc.ABC):
    """所有采集器的抽象基类。

    子类只需实现 :meth:`parse`，基类负责请求重试、代理轮换、
    请求头随机化以及请求间随机延迟，规避反爬机制。
    """

    name: str = "base"

    def __init__(self, timeout: int = REQUEST_TIMEOUT):
        self.timeout = timeout
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=REQUEST_RETRY_COUNT,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=5, pool_maxsize=5)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _request(self, url: str, **kwargs) -> Optional[requests.Response]:
        kwargs.setdefault("headers", random_headers())
        kwargs.setdefault("timeout", self.timeout)
        proxy = proxy_pool.get_proxy()
        if proxy:
            kwargs.setdefault("proxies", proxy)
        try:
            resp = self._session.get(url, **kwargs)
            if resp.status_code == 200:
                return resp
            logger.warning("[%s] %s 返回状态码 %d", self.name, url, resp.status_code)
            if proxy:
                proxy_pool.mark_bad(proxy)
        except requests.RequestException as exc:
            logger.warning("[%s] 请求 %s 失败: %s", self.name, url, exc)
            if proxy:
                proxy_pool.mark_bad(proxy)
        return None

    def _polite_delay(self):
        delay = random.uniform(*REQUEST_DELAY_RANGE)
        time.sleep(delay)

    @abc.abstractmethod
    def parse(self, html: str, base_url: str) -> List[CollectedItem]:
        """解析原始 HTML，返回结构化条目列表。"""

    def fetch(self, url: str) -> List[CollectedItem]:
        logger.info("[%s] 开始抓取 %s", self.name, url)
        resp = self._request(url)
        self._polite_delay()
        if resp is None:
            return []
        try:
            resp.encoding = resp.apparent_encoding
            items = self.parse(resp.text, url)
            logger.info("[%s] 解析到 %d 条结果", self.name, len(items))
            return items
        except Exception as exc:
            logger.exception("[%s] 解析 %s 失败: %s", self.name, url, exc)
            return []
