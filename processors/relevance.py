import math
import re
from typing import List

from config import RELEVANCE_THRESHOLD

_TOKEN_RE = re.compile(r"[\u4e00-\u9fa5]{1}|[a-zA-Z0-9]+", re.UNICODE)

_TITLE_WEIGHT = 3.0
_SUMMARY_WEIGHT = 2.0
_CONTENT_WEIGHT = 1.0
_TITLE_ONLY_WEIGHT = 1.2
_TITLE_ONLY_PENALTY = 0.5

TITLE_WEIGHT = _TITLE_WEIGHT
SUMMARY_WEIGHT = _SUMMARY_WEIGHT
CONTENT_WEIGHT = _CONTENT_WEIGHT
TITLE_ONLY_WEIGHT = _TITLE_ONLY_WEIGHT
TITLE_ONLY_PENALTY = _TITLE_ONLY_PENALTY


def _tokenize(text: str) -> List[str]:
    try:
        import jieba
        return [t for t in jieba.cut(text) if t.strip()]
    except ImportError:
        return _TOKEN_RE.findall(text.lower())


class RelevanceScorer:
    """主题相关性打分器。

    采用加权关键词匹配：标题命中权重最高，摘要次之，正文最低，
    以此过滤「只有标题沾边但实际无关」的垃圾内容。
    最终得分经归一化映射到 [0, 1] 区间，与 ``RELEVANCE_THRESHOLD``
    比较决定是否入库。
    """

    def __init__(self, keywords: List[str]):
        self.keywords = [k.strip().lower() for k in keywords if k and k.strip()]
        self._kw_tokens = {kw: _tokenize(kw) for kw in self.keywords}

    def score(self, title: str, summary: str = "", content: str = "") -> float:
        if not self.keywords:
            return 0.0
        title_l = (title or "").lower()
        summary_l = (summary or "").lower()
        content_l = (content or "").lower()

        title_tokens = set(_tokenize(title_l))
        summary_tokens = set(_tokenize(summary_l))
        content_tokens = set(_tokenize(content_l))

        total_weight = 0.0
        matched_weight = 0.0
        title_only_count = 0
        matched_count = 0
        for kw, tokens in self._kw_tokens.items():
            kw_len = len(tokens)
            total_weight += len(kw)
            in_title = self._match(kw, tokens, title_l, title_tokens)
            in_summary = self._match(kw, tokens, summary_l, summary_tokens)
            in_content = self._match(kw, tokens, content_l, content_tokens)

            if in_title and (in_summary or in_content):
                matched_weight += len(kw) * TITLE_WEIGHT
                matched_count += 1
            elif in_title:
                matched_weight += len(kw) * TITLE_ONLY_WEIGHT
                title_only_count += 1
                matched_count += 1
            elif in_summary:
                matched_weight += len(kw) * SUMMARY_WEIGHT
                matched_count += 1
            elif in_content:
                matched_weight += len(kw) * CONTENT_WEIGHT
                matched_count += 1

        if total_weight == 0:
            return 0.0
        coverage = matched_count / len(self.keywords)
        raw = matched_weight / (total_weight * TITLE_WEIGHT)
        score = min(1.0, math.log1p(raw * 5) / math.log1p(5.0))
        if matched_count > 0 and title_only_count == matched_count:
            score *= TITLE_ONLY_PENALTY
        return round(score * coverage, 4)

    @staticmethod
    def _match(keyword: str, kw_tokens: List[str], text: str, text_tokens: set) -> bool:
        if not keyword:
            return False
        if keyword in text:
            return True
        if kw_tokens and all(t in text_tokens for t in kw_tokens):
            return True
        return False

    def is_relevant(self, title: str, summary: str = "", content: str = "") -> bool:
        return self.score(title, summary, content) >= RELEVANCE_THRESHOLD
