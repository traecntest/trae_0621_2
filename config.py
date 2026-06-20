import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "aggregator.db"

DEFAULT_FETCH_INTERVAL_MINUTES = 60
MIN_FETCH_INTERVAL_MINUTES = 15

MAX_CONCURRENT_TASKS = 3
REQUEST_TIMEOUT = 15
REQUEST_RETRY_COUNT = 2
REQUEST_DELAY_RANGE = (1.0, 3.0)

RELEVANCE_THRESHOLD = 0.25
SIMHASH_BITS = 64
DEDUP_HAMMING_DISTANCE = 3

ENABLE_PROXY_POOL = False
PROXY_POOL_URL = ""
RANDOMIZE_HEADERS = True

NOTIFY_ON_RELEVANCE = 0.6
RELEVANCE_TOP_N_NOTIFY = 3

APP_TITLE = "目标驱动内容聚合器"
APP_VERSION = "0.1.0"
DISCLAIMER = (
    "本系统仅用于个人学习与研究，禁止用于任何商业用途。\n"
    "系统抓取的内容版权归原作者所有，使用者需自行承担合规风险。\n"
    "系统已内置访问频率限制，请勿擅自调高频率对目标站点造成过大负载。"
)

USER_AGENT_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]
