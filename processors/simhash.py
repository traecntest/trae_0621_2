import hashlib
import re
from collections import defaultdict
from typing import List

from config import SIMHASH_BITS

_TOKEN_RE = re.compile(r"[\u4e00-\u9fa5]{1}|[a-zA-Z0-9]+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    """通用分词：中文逐字 + 英文/数字连续串。

    若环境安装了 jieba 则优先使用其更精准的分词结果。
    """
    try:
        import jieba
        tokens = list(jieba.cut_for_search(text))
        return [t.strip() for t in tokens if t.strip()]
    except ImportError:
        return _TOKEN_RE.findall(text.lower())


class Simhash:
    """64 位 SimHash 文档指纹。

    通过对文本特征加权求和再二值化得到定长指纹，
    利用汉明距离判断两篇文档是否近似重复，
    防止同一篇文章跨平台被重复推送。
    """

    def __init__(self, value: int, bits: int = SIMHASH_BITS):
        self.bits = bits
        self.value = value & ((1 << bits) - 1)

    @classmethod
    def from_text(cls, text: str, bits: int = SIMHASH_BITS) -> "Simhash":
        if not text:
            return cls(0, bits)
        tokens = _tokenize(text)
        if not tokens:
            return cls(0, bits)
        vector = [0] * bits
        freq = defaultdict(int)
        for tok in tokens:
            freq[tok] += 1
        for tok, weight in freq.items():
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            for i in range(bits):
                if h & (1 << i):
                    vector[i] += weight
                else:
                    vector[i] -= weight
        fingerprint = 0
        for i in range(bits):
            if vector[i] > 0:
                fingerprint |= (1 << i)
        return cls(fingerprint, bits)

    def to_hex(self) -> str:
        return f"{self.value:0{self.bits // 4}x}"

    @classmethod
    def from_hex(cls, hex_str: str, bits: int = SIMHASH_BITS) -> "Simhash":
        return cls(int(hex_str, 16), bits)

    @staticmethod
    def hamming_distance(a, b) -> int:
        if isinstance(a, str):
            a = int(a, 16)
        if isinstance(b, str):
            b = int(b, 16)
        x = (a ^ b) & ((1 << SIMHASH_BITS) - 1)
        dist = 0
        while x:
            dist += 1
            x &= x - 1
        return dist

    def distance_to(self, other: "Simhash") -> int:
        return self.hamming_distance(self.value, other.value)

    def __str__(self):
        return self.to_hex()
