import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

KEYWORD_PROMPT = """你是一个动漫标题搜索助手。给定一个动漫标题（可能包含字幕组标签、集数、分辨率等信息），生成3-5个用于在TMDB或弹弹Play数据库中搜索该动漫的关键词。

考虑以下变体：
- 中文翻译名（简体/繁体）
- 日文原名
- 英文官方名
- 罗马音
- 常见缩写

标题: {title}

返回JSON格式的关键词列表，例如: {{"keywords": ["关键词1", "关键词2", "关键词3"]}}"""

MATCH_PROMPT = """你是一个动漫匹配助手。给定原始标题和搜索到的候选番剧列表，判断哪个候选是最佳匹配。

原始标题: {title}

候选列表:
{candidates}

返回JSON格式: {{"index": <最佳匹配的序号(0开始)>, "confidence": <置信度0-1>}}
如果没有任何候选匹配，返回: {{"index": -1, "confidence": 0}}"""


@dataclass
class MatchResult:
    matched_item: Any
    confidence: float


class AIMatcher:
    def __init__(self, openai_config: dict):
        self._client = OpenAI(
            api_key=openai_config.get("api_key", ""),
            base_url=openai_config.get("api_base", "https://api.openai.com/v1"),
        )
        self._model = openai_config.get("model", "gpt-3.5-turbo")
        self._confidence_threshold = 0.7

    def _call_llm(self, prompt: str) -> dict:
        """同步调用 LLM，返回解析后的 dict。"""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    async def _generate_keywords(self, title: str) -> list[str]:
        result = await asyncio.to_thread(
            self._call_llm, KEYWORD_PROMPT.format(title=title)
        )
        return result.get("keywords", [])

    def _deduplicate(
        self, results: list[dict], key_fn: Callable
    ) -> list[dict]:
        seen = set()
        deduped = []
        for item in results:
            key = key_fn(item)
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        return deduped

    async def _pick_best_match(
        self, title: str, candidates: list[dict], formatter: Callable
    ) -> Optional[MatchResult]:
        if not candidates:
            return None

        formatted = formatter(candidates)
        result = await asyncio.to_thread(
            self._call_llm,
            MATCH_PROMPT.format(title=title, candidates=formatted),
        )

        index = result.get("index", -1)
        confidence = result.get("confidence", 0)

        if index < 0 or confidence < self._confidence_threshold:
            return None

        return MatchResult(matched_item=candidates[index], confidence=confidence)

    async def search_and_match(
        self,
        title: str,
        search_fn: Callable,
        result_formatter: Callable,
        dedup_key: Optional[Callable] = None,
    ) -> Optional[MatchResult]:
        keywords = await self._generate_keywords(title)
        if not keywords:
            logger.debug("[AIMatcher] No keywords generated for: %s", title)
            return None

        all_results: list[dict] = []
        for keyword in keywords:
            results = await search_fn(keyword)
            all_results.extend(results)
            await asyncio.sleep(0.25)

        if not all_results:
            logger.debug("[AIMatcher] No search results for: %s", title)
            return None

        if dedup_key:
            all_results = self._deduplicate(all_results, dedup_key)

        return await self._pick_best_match(title, all_results, result_formatter)
