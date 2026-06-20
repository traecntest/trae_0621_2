import logging
import random
import threading
import time
from typing import List, Optional

import requests

from config import ENABLE_PROXY_POOL, PROXY_POOL_URL
from collectors.headers import random_headers

logger = logging.getLogger(__name__)


class ProxyPool:
    """IP 代理池轮换机制。

    当 ``ENABLE_PROXY_POOL`` 关闭时退化为直连模式，保证系统在无代理时仍可运行。
    """

    def __init__(self, enabled: bool = None, api_url: str = None):
        self.enabled = ENABLE_PROXY_POOL if enabled is None else enabled
        self.api_url = api_url or PROXY_POOL_URL
        self._proxies: List[dict] = []
        self._lock = threading.Lock()
        self._last_fetch = 0.0
        self._ttl = 300

    def _fetch_proxies(self):
        if not self.enabled or not self.api_url:
            return
        now = time.time()
        if self._proxies and now - self._last_fetch < self._ttl:
            return
        try:
            resp = requests.get(self.api_url, headers=random_headers(), timeout=10)
            raw = resp.text.strip().splitlines()
            with self._lock:
                self._proxies = [
                    {"http": f"http://{p}", "https": f"http://{p}"} for p in raw if p
                ]
                self._last_fetch = now
            logger.info("代理池刷新完成，共 %d 个代理", len(self._proxies))
        except Exception as exc:
            logger.warning("代理池刷新失败: %s", exc)

    def get_proxy(self) -> Optional[dict]:
        self._fetch_proxies()
        with self._lock:
            if not self._proxies:
                return None
            return random.choice(self._proxies)

    def mark_bad(self, proxy: dict):
        with self._lock:
            if proxy in self._proxies:
                self._proxies.remove(proxy)
                logger.debug("移除失效代理，剩余 %d 个", len(self._proxies))


proxy_pool = ProxyPool()
