# AI 增强搜索与弹弹 Play 番名对齐 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 AutoBangumi 添加 AI 增强搜索（TMDB 搜索失败时用 LLM 提高匹配率）和弹弹 Play 番名对齐（重命名文件名与弹弹 Play 弹幕库匹配）。

**Architecture:** 抽象通用 AIMatcher 模块（AI 生成关键词 → 搜索 → 去重 → AI 决策），功能 A（TMDB 搜索）和功能 B（弹弹 Play 搜索）共用。弹弹 Play 客户端独立模块，支持签名认证。重命名通过扩展 renamer 的 _batch_lookup_offsets 返回 dandanplay_title 实现。

**Tech Stack:** Python 3.10+, FastAPI, SQLModel, OpenAI API (兼容格式), 弹弹 Play API v2

---

## Task 1: 数据模型与配置基础

**Files:**
- Modify: `backend/src/module/models/bangumi.py:8-92` (Bangumi, BangumiUpdate)
- Modify: `backend/src/module/models/config.py:195-266` (DandanplayConfig, Config)
- Modify: `backend/src/module/conf/const.py:44-52,53-67` (default config)
- Modify: `backend/src/module/database/combine.py:26,113` (migration)
- Test: `backend/src/test/test_ai_search_dandanplay.py`

### Step 1: 编写数据模型测试

```python
# backend/src/test/test_ai_search_dandanplay.py

import pytest
from module.models.bangumi import Bangumi, BangumiUpdate
from module.models.config import Config


class TestBangumiDandanplayField:
    def test_bangumi_has_dandanplay_title(self):
        b = Bangumi(official_title="test")
        assert hasattr(b, "dandanplay_title")
        assert b.dandanplay_title is None

    def test_bangumi_has_dandanplay_retry_count(self):
        b = Bangumi(official_title="test")
        assert hasattr(b, "dandanplay_retry_count")
        assert b.dandanplay_retry_count == 0

    def test_bangumi_update_has_dandanplay_title(self):
        u = BangumiUpdate()
        assert hasattr(u, "dandanplay_title")
        # BangumiUpdate 字段应该可选
        u = BangumiUpdate(official_title="test", dandanplay_title="some title")
        assert u.dandanplay_title == "some title"


class TestDandanplayConfig:
    def test_config_has_dandanplay(self):
        config = Config()
        assert hasattr(config, "dandanplay")
        assert config.dandanplay.enable is False
        assert config.dandanplay.app_id == ""
        assert config.dandanplay.app_secret == ""

    def test_dandanplay_defaults(self):
        config = Config()
        assert config.dandanplay.enable is False
```

### Step 2: 运行测试确认失败

Run: `cd backend && uv run pytest src/test/test_ai_search_dandanplay.py -v`
Expected: FAIL - `AttributeError: 'Bangumi' object has no attribute 'dandanplay_title'`

### Step 3: 添加 Bangumi 模型字段

在 `backend/src/module/models/bangumi.py` 的 `Bangumi` 类中，在 `title_aliases` 字段后添加：

```python
    dandanplay_title: Optional[str] = Field(
        default=None, alias="dandanplay_title", title="弹弹Play标题"
    )
    dandanplay_retry_count: int = Field(
        default=0, alias="dandanplay_retry_count", title="弹弹Play重试次数"
    )
```

在 `BangumiUpdate` 类中添加：

```python
    dandanplay_title: Optional[str] = Field(
        default=None, alias="dandanplay_title", title="弹弹Play标题"
    )
```

### Step 4: 添加 DandanplayConfig 配置模型

在 `backend/src/module/models/config.py` 的 `ExperimentalOpenAI` 类后添加：

```python
class DandanplayConfig(BaseModel):
    """Dandanplay API configuration for danmaku title alignment."""

    enable: bool = Field(False, description="Enable Dandanplay integration")
    app_id: str = Field("", description="Dandanplay AppId")
    app_secret: str = Field("", description="Dandanplay AppSecret")
```

在 `Config` 类中添加字段（`experimental_openai` 之后）：

```python
    dandanplay: DandanplayConfig = DandanplayConfig()
```

### Step 5: 添加默认配置

在 `backend/src/module/conf/const.py` 的 `DEFAULT_SETTINGS` 中，`experimental_openai` 之后添加：

```python
    "dandanplay": {
        "enable": False,
        "app_id": "",
        "app_secret": "",
    },
```

### Step 6: 添加数据库迁移

在 `backend/src/module/database/combine.py` 中：

1. `CURRENT_SCHEMA_VERSION` 改为 `10`
2. 在 `MIGRATIONS` 列表末尾添加：

```python
    (
        10,
        "add dandanplay_title and retry count to bangumi",
        [
            "ALTER TABLE bangumi ADD COLUMN dandanplay_title TEXT DEFAULT NULL",
            "ALTER TABLE bangumi ADD COLUMN dandanplay_retry_count INTEGER DEFAULT 0",
        ],
    ),
```

3. 在 `run_migrations` 方法中（约第 209 行之后），添加 version 10 的列存在性检查：

```python
        if "bangumi" in tables and version == 10:
            columns = [col["name"] for col in inspector.get_columns("bangumi")]
            if "dandanplay_title" in columns:
                needs_run = False
```

### Step 7: 运行测试确认通过

Run: `cd backend && uv run pytest src/test/test_ai_search_dandanplay.py -v`
Expected: PASS

### Step 8: Commit

```bash
git add backend/src/module/models/bangumi.py backend/src/module/models/config.py backend/src/module/conf/const.py backend/src/module/database/combine.py backend/src/test/test_ai_search_dandanplay.py
git commit -m "feat: add dandanplay config, bangumi fields, and database migration"
```

---

## Task 2: AIMatcher 通用模块

**Files:**
- Create: `backend/src/module/searcher/ai_matcher.py`
- Test: `backend/src/test/test_ai_matcher.py`

### Step 1: 编写 AIMatcher 测试

```python
# backend/src/test/test_ai_matcher.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from module.searcher.ai_matcher import AIMatcher, MatchResult


class TestAIMatcherGenerateKeywords:
    @pytest.mark.asyncio
    async def test_generate_keywords_returns_list(self):
        """LLM 应返回关键词列表"""
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {
            "keywords": ["葬送的芙莉莲", "Frieren", "Sousou no Frieren"]
        }
        matcher = AIMatcher.__new__(AIMatcher)
        matcher._parser = mock_parser

        keywords = await matcher._generate_keywords("葬送的芙莉莲 S01E01")
        assert keywords == ["葬送的芙莉莲", "Frieren", "Sousou no Frieren"]

    @pytest.mark.asyncio
    async def test_generate_keywords_empty_result(self):
        """LLM 返回空结果时应返回空列表"""
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {"keywords": []}
        matcher = AIMatcher.__new__(AIMatcher)
        matcher._parser = mock_parser

        keywords = await matcher._generate_keywords("test")
        assert keywords == []


class TestAIMatcherDeduplicate:
    def test_deduplicate_by_id(self):
        """相同 ID 的结果应去重"""
        results = [
            {"id": 1, "name": "A"},
            {"id": 2, "name": "B"},
            {"id": 1, "name": "A (duplicate)"},
        ]
        matcher = AIMatcher.__new__(AIMatcher)
        deduped = matcher._deduplicate(results, key_fn=lambda x: x["id"])
        assert len(deduped) == 2
        assert deduped[0]["id"] == 1


class TestAIMatcherSearchAndMatch:
    @pytest.mark.asyncio
    async def test_search_and_match_success(self):
        """完整流程：生成关键词 → 搜索 → 去重 → AI 决策"""
        mock_parser = MagicMock()
        mock_parser.parse.side_effect = [
            {"keywords": ["keyword1"]},
            {"index": 0, "confidence": 0.9},
        ]

        async def mock_search(keyword):
            return [{"id": 1, "name": "Test Anime"}]

        def mock_formatter(results):
            return "1. Test Anime"

        with patch("module.searcher.ai_matcher.OpenAIParser", return_value=mock_parser):
            matcher = AIMatcher(openai_config={"api_key": "test"})
            result = await matcher.search_and_match(
                title="Test",
                search_fn=mock_search,
                result_formatter=mock_formatter,
            )

        assert result is not None
        assert result.confidence == 0.9
        assert result.matched_item["name"] == "Test Anime"

    @pytest.mark.asyncio
    async def test_search_and_match_no_results(self):
        """搜索无结果时应返回 None"""
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {"keywords": ["keyword1"]}

        async def mock_search(keyword):
            return []

        with patch("module.searcher.ai_matcher.OpenAIParser", return_value=mock_parser):
            matcher = AIMatcher(openai_config={"api_key": "test"})
            result = await matcher.search_and_match(
                title="Test",
                search_fn=mock_search,
                result_formatter=lambda r: "",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_search_and_match_low_confidence(self):
        """置信度低于阈值时应返回 None"""
        mock_parser = MagicMock()
        mock_parser.parse.side_effect = [
            {"keywords": ["keyword1"]},
            {"index": 0, "confidence": 0.3},
        ]

        async def mock_search(keyword):
            return [{"id": 1, "name": "Test"}]

        with patch("module.searcher.ai_matcher.OpenAIParser", return_value=mock_parser):
            matcher = AIMatcher(openai_config={"api_key": "test"})
            result = await matcher.search_and_match(
                title="Test",
                search_fn=mock_search,
                result_formatter=lambda r: "1. Test",
            )

        assert result is None
```

### Step 2: 运行测试确认失败

Run: `cd backend && uv run pytest src/test/test_ai_matcher.py -v`
Expected: FAIL - `ModuleNotFoundError`

### Step 3: 实现 AIMatcher

创建 `backend/src/module/searcher/ai_matcher.py`：

> **关键设计**: 不复用 `OpenAIParser.parse()`，因为它内部硬编码了 `response_format=Episode`（Pydantic response model）。AIMatcher 需要自己的 Pydantic response models（`KeywordResponse`、`MatchResponse`），直接使用 OpenAI 客户端调用。

```python
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
        content = response.choices[0].message.content
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
            # 间隔 250ms 避免触发 API rate limit
            await asyncio.sleep(0.25)

        if not all_results:
            logger.debug("[AIMatcher] No search results for: %s", title)
            return None

        if dedup_key:
            all_results = self._deduplicate(all_results, dedup_key)

        return await self._pick_best_match(title, all_results, result_formatter)
```

> **注意**: 使用 `asyncio.to_thread()` 而非 `asyncio.get_event_loop().run_in_executor()`（Python 3.10+ 推荐）。使用 `response_format={"type": "json_object"}` 确保返回 JSON。

### Step 4: 更新测试 mock

由于 AIMatcher 不再使用 `OpenAIParser`，测试需要 mock `OpenAI` 客户端。更新 Task 2 Step 1 中的测试：

```python
class TestAIMatcherSearchAndMatch:
    async def test_search_and_match_success(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"index": 0, "confidence": 0.9}'

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        # 第一次调用返回关键词，第二次返回匹配结果
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(
                content='{"keywords": ["keyword1"]}'
            ))]),
            MagicMock(choices=[MagicMock(message=MagicMock(
                content='{"index": 0, "confidence": 0.9}'
            ))]),
        ]

        with patch("module.searcher.ai_matcher.OpenAI", return_value=mock_client):
            matcher = AIMatcher(openai_config={"api_key": "test"})
            result = await matcher.search_and_match(
                title="Test",
                search_fn=mock_search,
                result_formatter=mock_formatter,
            )
        # ... assertions unchanged
```

> **实现注意**: 测试中 `mock_client` 需要处理 `side_effect` 来区分两次 LLM 调用（关键词生成 + 匹配决策）。

### Step 4: 运行测试确认通过

Run: `cd backend && uv run pytest src/test/test_ai_matcher.py -v`
Expected: PASS

### Step 5: Commit

```bash
git add backend/src/module/searcher/ai_matcher.py backend/src/test/test_ai_matcher.py
git commit -m "feat: add AIMatcher module for AI-assisted search and match"
```

---

## Task 3: 弹弹 Play API 客户端

**Files:**
- Create: `backend/src/module/searcher/dandanplay.py`
- Test: `backend/src/test/test_dandanplay.py`

### Step 1: 编写弹弹 Play 客户端测试

```python
# backend/src/test/test_dandanplay.py

import hashlib
import base64
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from module.searcher.dandanplay import DandanplayClient, generate_signature


class TestGenerateSignature:
    def test_signature_format(self):
        """签名应该是 base64(sha256(appid+timestamp+path+secret))"""
        sig = generate_signature("test_id", 1234567890, "/api/v2/search/anime", "test_secret")
        # 验证是 base64 格式
        decoded = base64.b64decode(sig)
        assert len(decoded) == 32  # SHA256 = 32 bytes

    def test_signature_deterministic(self):
        """相同输入应产生相同签名"""
        sig1 = generate_signature("id", 100, "/path", "secret")
        sig2 = generate_signature("id", 100, "/path", "secret")
        assert sig1 == sig2


class TestDandanplayClient:
    @pytest.mark.asyncio
    async def test_search_returns_title(self):
        """搜索成功应返回第一个结果的 animeTitle"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "animes": [
                {"animeTitle": "葬送的芙莉莲", "animeId": 123},
                {"animeTitle": "其他番剧", "animeId": 456},
            ]
        }
        mock_response.status_code = 200

        mock_session = AsyncMock()
        mock_session.get.return_value = mock_response

        client = DandanplayClient(app_id="test", app_secret="test")
        with patch("module.searcher.dandanplay.httpx.AsyncClient", return_value=mock_session):
            result = await client.search("葬送的芙莉莲")

        assert result == "葬送的芙莉莲"

    @pytest.mark.asyncio
    async def test_search_no_results(self):
        """搜索无结果应返回 None"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"animes": []}
        mock_response.status_code = 200

        mock_session = AsyncMock()
        mock_session.get.return_value = mock_response

        client = DandanplayClient(app_id="test", app_secret="test")
        with patch("module.searcher.dandanplay.httpx.AsyncClient", return_value=mock_session):
            result = await client.search("不存在的番剧")

        assert result is None
```

### Step 2: 运行测试确认失败

Run: `cd backend && uv run pytest src/test/test_dandanplay.py -v`
Expected: FAIL - `ModuleNotFoundError`

### Step 3: 检查 httpx 依赖

Run: `cd backend && uv run python -c "import httpx; print(httpx.__version__)"`
如果未安装：`cd backend && uv add httpx`

### Step 4: 实现弹弹 Play 客户端

创建 `backend/src/module/searcher/dandanplay.py`：

```python
import asyncio
import base64
import hashlib
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.dandanplay.net"


def generate_signature(
    app_id: str, timestamp: int, path: str, app_secret: str
) -> str:
    data = f"{app_id}{timestamp}{path}{app_secret}"
    sha256_hash = hashlib.sha256(data.encode()).digest()
    return base64.b64encode(sha256_hash).decode()


class DandanplayClient:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret

    def _build_headers(self, path: str) -> dict[str, str]:
        timestamp = int(time.time())
        signature = generate_signature(
            self.app_id, timestamp, path, self.app_secret
        )
        return {
            "X-AppId": self.app_id,
            "X-Timestamp": str(timestamp),
            "X-Signature": signature,
        }

    async def search(self, keyword: str) -> Optional[str]:
        """搜索番剧，返回第一个匹配的 animeTitle，无结果返回 None。"""
        path = "/api/v2/search/anime"
        headers = self._build_headers(path)
        url = f"{BASE_URL}{path}"
        params = {"keyword": keyword, "withRelated": "false"}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code != 200:
                    logger.warning(
                        "[Dandanplay] Search failed with status %d for: %s",
                        resp.status_code,
                        keyword,
                    )
                    return None

                data = resp.json()
                animes = data.get("animes", [])
                if animes:
                    return animes[0].get("animeTitle")

                return None
        except httpx.HTTPError as e:
            logger.warning("[Dandanplay] HTTP error for '%s': %s", keyword, e)
            return None
```

### Step 5: 运行测试确认通过

Run: `cd backend && uv run pytest src/test/test_dandanplay.py -v`
Expected: PASS

### Step 6: Commit

```bash
git add backend/src/module/searcher/dandanplay.py backend/src/test/test_dandanplay.py
git commit -m "feat: add Dandanplay API client with signature auth"
```

---

## Task 4: 功能 A — AI 增强搜索集成

**Files:**
- Modify: `backend/src/module/rss/analyser.py:15-35` (official_title_parser)
- Test: `backend/src/test/test_ai_search_integration.py`

### Step 1: 编写集成测试

```python
# backend/src/test/test_ai_search_integration.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestAIEnhancedSearch:
    @pytest.mark.asyncio
    async def test_ai_search_triggered_when_tmdb_fails(self):
        """当 TMDB 搜索失败（official_title == title_raw）时，应触发 AI 增强"""
        # 此测试验证触发条件，具体集成在 analyser 中
        # 模拟场景：raw_parser 返回 bangumi，tmdb 未修改 official_title
        from module.models.bangumi import Bangumi

        bangumi = Bangumi(
            title_raw="Frieren S01",
            official_title="Frieren S01",  # 未被 TMDB 替换
            season=1,
        )
        # official_title == title_raw 说明 TMDB 搜索失败
        assert bangumi.official_title == bangumi.title_raw

    @pytest.mark.asyncio
    async def test_ai_search_not_triggered_when_tmdb_succeeds(self):
        """当 TMDB 搜索成功时，不应触发 AI 增强"""
        from module.models.bangumi import Bangumi

        bangumi = Bangumi(
            title_raw="Frieren S01",
            official_title="葬送的芙莉莲",  # TMDB 替换了标题
            season=1,
        )
        assert bangumi.official_title != bangumi.title_raw
```

### Step 2: 修改 RSSAnalyser

在 `backend/src/module/rss/analyser.py` 的 `official_title_parser` 方法中添加 AI 增强逻辑。

**触发条件改进**: 不依赖 `official_title == title_raw` 字符串比较（不可靠），而是在 `official_title_parser` 内部用局部变量 `tmdb_matched = False` 标记 TMDB 是否成功匹配，仅在 `tmdb_matched == False` 时触发 AI 增强。

```python
    async def official_title_parser(self, bangumi, rss, torrent=None):
        tmdb_matched = False

        if rss and rss.parser == "mikan" and rss.homepage:
            try:
                # ... 现有 mikan 解析逻辑 ...
                tmdb_matched = True  # mikan 成功
            except (AttributeError, Exception):
                logger.warning("...")

        if rss and rss.parser == "tmdb":
            try:
                title, season, year, poster_link = self.tmdb_parser(
                    bangumi.title_raw, bangumi.season
                )
                if title and title != bangumi.title_raw:
                    bangumi.official_title = title
                    tmdb_matched = True
                # ... 现有 tmdb 逻辑 ...
            except Exception:
                logger.warning("...")

        # AI 增强搜索：TMDB/Mikan 均未成功匹配时触发
        if settings.experimental_openai.enable and not tmdb_matched:
            from module.searcher.ai_matcher import AIMatcher
            try:
                kwargs = settings.experimental_openai.dict(exclude={"enable"})
                matcher = AIMatcher(openai_config=kwargs)

                async def tmdb_search_fn(keyword: str) -> list[dict]:
                    from module.parser.analyser.tmdb_parser import tmdb_parser
                    result = tmdb_parser(keyword, settings.rss_parser.language)
                    if result is None:
                        return []
                    return [{"id": result.id, "title": result.title,
                             "original_title": result.original_title}]

                def tmdb_formatter(results: list[dict]) -> str:
                    lines = []
                    for i, r in enumerate(results):
                        lines.append(f"{i+1}. {r['title']} ({r.get('original_title', '')}) [TMDB ID: {r['id']}]")
                    return "\n".join(lines)

                match = await matcher.search_and_match(
                    title=bangumi.title_raw,
                    search_fn=tmdb_search_fn,
                    result_formatter=tmdb_formatter,
                    dedup_key=lambda x: x["id"],
                )

                if match and match.confidence >= 0.7:
                    bangumi.official_title = match.matched_item["title"]
                    logger.info(
                        "[AI] Enhanced search matched: %s (confidence=%.2f)",
                        bangumi.official_title,
                        match.confidence,
                    )
            except Exception as e:
                logger.warning("[AI] Enhanced search failed: %s", e)
```

> **实现注意**: 需要先读取 `analyser.py` 的完整内容，理解现有的 `official_title_parser` 控制流，在正确的位置插入 AI 增强逻辑。关键是确保 AI 增强在 Mikan/TMDB 搜索都尝试过后才触发。使用 `tmdb_matched` 局部变量标记是否成功，比字符串比较更可靠。

### Step 3: 运行测试

Run: `cd backend && uv run pytest src/test/test_ai_search_integration.py -v`
Expected: PASS

### Step 4: Commit

```bash
git add backend/src/module/rss/analyser.py backend/src/test/test_ai_search_integration.py
git commit -m "feat: integrate AI enhanced search in RSS analyser"
```

---

## Task 5: 功能 B — 弹弹 Play 番名获取

**Files:**
- Modify: `backend/src/module/database/bangumi.py` (新增查询和更新方法)
- Modify: `backend/src/module/rss/analyser.py` (bangumi 创建后获取 dandanplay_title)
- Test: `backend/src/test/test_dandanplay_fetch.py`

### Step 1: 编写弹弹 Play 获取测试

```python
# backend/src/test/test_dandanplay_fetch.py

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestDandanplayFetch:
    @pytest.mark.asyncio
    async def test_fetch_dandanplay_title_success(self):
        """成功获取弹弹 Play 番名应写入 dandanplay_title"""
        mock_client = AsyncMock()
        mock_client.search.return_value = "葬送的芙莉莲"

        with patch("module.searcher.dandanplay.DandanplayClient", return_value=mock_client):
            from module.searcher.dandanplay import fetch_dandanplay_title

            result = await fetch_dandanplay_title("Frieren", "app_id", "app_secret")
            assert result == "葬送的芙莉莲"

    @pytest.mark.asyncio
    async def test_fetch_dandanplay_title_no_result(self):
        """弹弹 Play 无结果应返回 None"""
        mock_client = AsyncMock()
        mock_client.search.return_value = None

        with patch("module.searcher.dandanplay.DandanplayClient", return_value=mock_client):
            from module.searcher.dandanplay import fetch_dandanplay_title

            result = await fetch_dandanplay_title("unknown", "app_id", "app_secret")
            assert result is None
```

### Step 2: 在 dandanplay.py 中添加 fetch 函数

在 `backend/src/module/searcher/dandanplay.py` 末尾添加：

```python
async def fetch_dandanplay_title(
    official_title: str, app_id: str, app_secret: str
) -> Optional[str]:
    """用官方标题搜索弹弹 Play，返回匹配的番名。"""
    if not official_title or not app_id:
        return None
    client = DandanplayClient(app_id=app_id, app_secret=app_secret)
    return await client.search(official_title)
```

### Step 3: 在 Database 中添加弹弹 Play 更新方法

在 `backend/src/module/database/bangumi.py` 中添加方法：

```python
    def update_dandanplay_title(self, bangumi_id: int, title: Optional[str]):
        """Update dandanplay_title for a bangumi."""
        bangumi = self.search_id(bangumi_id)
        if bangumi:
            bangumi.dandanplay_title = title
            if title is None:
                bangumi.dandanplay_retry_count += 1
            else:
                bangumi.dandanplay_retry_count = 0
            self.session.commit()

    def get_bangumi_missing_dandanplay(self) -> list:
        """Get bangumi records missing dandanplay_title (retry count < 3)."""
        from sqlmodel import select
        condition = select(Bangumi).where(
            and_(
                Bangumi.dandanplay_title.is_(None),
                Bangumi.dandanplay_retry_count < 3,
                Bangumi.deleted == False,
            )
        )
        result = self.session.execute(condition)
        return list(result.scalars().all())
```

### Step 4: 在 analyser.py 中 bangumi 创建后获取 dandanplay_title

在 bangumi 数据写入数据库之后（`analyser.py` 的 `rss_to_data` 或相关流程中），添加异步获取弹弹 Play 番名的逻辑。条件：`settings.bangumi_manage.rename_method == "dandanplay"` 且 `settings.dandanplay.enable`。

> **实现注意**: 需要读取 analyser.py 中 bangumi 写入数据库的具体位置，在写入后触发异步弹弹 Play 搜索。

### Step 5: 运行测试

Run: `cd backend && uv run pytest src/test/test_dandanplay_fetch.py -v`
Expected: PASS

### Step 6: Commit

```bash
git add backend/src/module/searcher/dandanplay.py backend/src/module/database/bangumi.py backend/src/test/test_dandanplay_fetch.py
git commit -m "feat: add dandanplay title fetch and database methods"
```

---

## Task 6: 后台补全任务 + Renamer 变更

**Files:**
- Modify: `backend/src/module/core/sub_thread.py` (新增 DandanplayThread)
- Modify: `backend/src/module/manager/renamer.py` (dandanplay rename method)
- Modify: `backend/src/module/manager/renamer.py:272-363` (_batch_lookup_offsets)
- Test: `backend/src/test/test_dandanplay_background.py`
- Test: `backend/src/test/test_renamer_dandanplay.py`

### Step 1: 编写后台补全测试

```python
# backend/src/test/test_dandanplay_background.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestDandanplayBackgroundTask:
    @pytest.mark.asyncio
    async def test_background_task_skips_records_with_retry_exceeded(self):
        """重试次数 >= 3 的记录应被跳过"""
        mock_db = MagicMock()
        mock_db.bangumi.get_bangumi_missing_dandanplay.return_value = [
            MagicMock(id=1, official_title="Test1", dandanplay_retry_count=0),
            MagicMock(id=2, official_title="Test2", dandanplay_retry_count=2),
        ]

        mock_client = AsyncMock()
        mock_client.search.side_effect = ["Title1", None]

        with patch("module.searcher.dandanplay.DandanplayClient", return_value=mock_client):
            from module.searcher.dandanplay import batch_update_dandanplay_titles

            await batch_update_dandanplay_titles(
                records=mock_db.bangumi.get_bangumi_missing_dandanplay(),
                db=mock_db,
                app_id="test",
                app_secret="test",
            )

            assert mock_db.bangumi.update_dandanplay_title.call_count == 2
```

### Step 2: 在 dandanplay.py 中添加批量更新函数

```python
async def batch_update_dandanplay_titles(
    records: list, db, app_id: str, app_secret: str
):
    """批量更新弹弹 Play 番名。"""
    client = DandanplayClient(app_id=app_id, app_secret=app_secret)
    for record in records:
        try:
            title = await client.search(record.official_title)
            db.update_dandanplay_title(record.id, title)
            if title:
                logger.info(
                    "[Dandanplay] Matched '%s' → '%s'",
                    record.official_title,
                    title,
                )
            else:
                logger.debug(
                    "[Dandanplay] No match for '%s' (retry=%d)",
                    record.official_title,
                    record.dandanplay_retry_count,
                )
        except Exception as e:
            logger.warning("[Dandanplay] Error updating '%s': %s", record.official_title, e)
            db.update_dandanplay_title(record.id, None)
```

### Step 3: 添加后台线程

在 `backend/src/module/core/sub_thread.py` 中添加 `DandanplayThread`，参考 `CalendarRefreshThread` 的模式（24小时间隔）。

### Step 4: 编写 renamer dandanplay 测试

```python
# backend/src/test/test_renamer_dandanplay.py

import pytest
from module.manager.renamer import Renamer


class TestRenamerDandanplayMethod:
    def test_gen_path_dandanplay_with_title(self):
        """dandanplay 方法应使用 dandanplay_title"""
        from module.models.bangumi import EpisodeFile

        file_info = EpisodeFile(
            title="E", season=1, episode=1, suffix=".mkv", media_path="/test.mkv"
        )
        result = Renamer.gen_path(file_info, "葬送的芙莉莲", "dandanplay")
        assert result == "葬送的芙莉莲 S01E01.mkv"

    def test_gen_path_dandanplay_fallback(self):
        """dandanplay_title 为空时应 fallback 到 advance 行为"""
        from module.models.bangumi import EpisodeFile

        file_info = EpisodeFile(
            title="E", season=1, episode=1, suffix=".mkv", media_path="/test.mkv"
        )
        result = Renamer.gen_path(file_info, "Frieren", "dandanplay")
        assert result == "Frieren S01E01.mkv"

    def test_gen_path_subtitle_dandanplay(self):
        """subtitle_dandanplay 方法应使用 dandanplay_title"""
        from module.models.bangumi import SubtitleFile

        file_info = SubtitleFile(
            title="E", season=1, episode=1,
            suffix=".ass", language=".zh", media_path="/test.ass"
        )
        result = Renamer.gen_path(file_info, "葬送的芙莉莲", "subtitle_dandanplay")
        assert result == "葬送的芙莉莲 S01E01.zh.ass"
```

### Step 5: 修改 renamer

在 `backend/src/module/manager/renamer.py` 中：

1. 在文件顶部添加 `RenameInfo` 定义：
```python
from typing import NamedTuple, Optional

class RenameInfo(NamedTuple):
    episode_offset: int
    season_offset: int
    dandanplay_title: Optional[str]
```

2. `gen_path` 添加 `dandanplay` 和 `subtitle_dandanplay` 分支（逻辑与 advance/subtitle_advance 完全相同，因为 `bangumi_name` 已在上层替换为 dandanplay_title 或 fallback 的 official_title）：
```python
        elif method == "dandanplay":
            return f"{bangumi_name} S{season}E{episode}{file_info.suffix}"
        elif method == "subtitle_dandanplay":
            return f"{bangumi_name} S{season}E{episode}.{file_info.language}{file_info.suffix}"
```

3. `_batch_lookup_offsets` 返回类型从 `dict[str, tuple[int, int]]` 改为 `dict[str, RenameInfo]`，在批量查询 bangumi 时一并获取 `dandanplay_title`：
```python
    def _batch_lookup_offsets(
        self, torrents_info: list[dict]
    ) -> dict[str, "RenameInfo"]:
        # ... 现有逻辑不变，但存储时用 RenameInfo ...
        # 原来: result[torrent_hash] = (b.episode_offset, b.season_offset)
        # 改为:
        result[torrent_hash] = RenameInfo(
            episode_offset=b.episode_offset,
            season_offset=b.season_offset,
            dandanplay_title=getattr(b, "dandanplay_title", None),
        )
```

4. `rename()` 方法中适配新的返回类型和 dandanplay 名称替换：
```python
        for info, files in zip(torrents_info, all_files):
            # ...
            rename_info = offset_map.get(torrent_hash, RenameInfo(0, 0, None))
            episode_offset = rename_info.episode_offset
            season_offset = rename_info.season_offset

            # dandanplay 名称替换：当 rename_method 为 dandanplay 时，
            # 用 dandanplay_title 替换 bangumi_name（仅影响文件名，不影响文件夹名）
            bangumi_name, season = self._path_to_bangumi(save_path, torrent_name)
            if (
                rename_method in ("dandanplay", "subtitle_dandanplay")
                and rename_info.dandanplay_title
            ):
                bangumi_name = rename_info.dandanplay_title
```

### Step 6: 运行所有新增测试

Run: `cd backend && uv run pytest src/test/test_dandanplay_background.py src/test/test_renamer_dandanplay.py -v`
Expected: PASS

### Step 7: Commit

```bash
git add backend/src/module/core/sub_thread.py backend/src/module/manager/renamer.py backend/src/test/test_dandanplay_background.py backend/src/test/test_renamer_dandanplay.py
git commit -m "feat: add dandanplay background task and renamer integration"
```

---

## Task 7: 前端配置

**Files:**
- Modify: `webui/types/config.ts`
- Modify: `webui/src/components/setting/config-manage.vue`
- Modify: `webui/src/i18n/zh-CN.json` (JSON 格式，不是 TypeScript)
- Modify: `webui/src/i18n/en-US.json`

### Step 1: 更新 TypeScript 类型

在 `webui/types/config.ts` 中：
1. 添加 `DandanplayConfig` 接口
2. 在 `Config` 接口中添加 `dandanplay` 字段
3. 在 `initConfig` 中添加默认值
4. 在 `BangumiManage` 的 `rename_method` 类型中添加 `"dandanplay"`

### Step 2: 更新配置组件

在 `webui/src/components/setting/config-manage.vue` 中：
1. 在 rename_method 的选项中添加 "dandanplay"

### Step 3: 添加 i18n 翻译

在 `webui/src/i18n/locales/zh-CN.ts` 和 `en-US.ts` 中添加：
- dandanplay rename method 的显示名称
- dandanplay 配置项的标签

### Step 4: Commit

```bash
git add webui/
git commit -m "feat: add dandanplay config UI and i18n translations"
```

---

## Task 8: 首次切换 rename_method 时的全量补全

**Files:**
- Modify: `backend/src/module/api/config.py` (配置更新 API)
- Test: `backend/src/test/test_dandanplay_batch_trigger.py`

### Step 1: 编写测试

```python
# backend/src/test/test_dandanplay_batch_trigger.py

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestBatchTriggerOnMethodSwitch:
    async def test_batch_triggered_when_switching_to_dandanplay(self):
        """当 rename_method 从非 dandanplay 切换到 dandanplay 时，应触发全量补全"""
        # 验证配置更新 API 在检测到 rename_method 变更时触发 batch_update
        pass  # 实现 API 集成后再补充具体测试
```

### Step 2: 在配置更新 API 中检测 rename_method 变更

在 `backend/src/module/api/config.py` 的配置更新逻辑中，检测 `rename_method` 是否从非 `"dandanplay"` 变为 `"dandanplay"`。如果是，且 `dandanplay.enable` 为 True，则触发 `batch_update_dandanplay_titles` 全量补全。

> **实现注意**: 需要读取 `config.py` 中的配置更新逻辑，在保存新配置前比较新旧 `rename_method` 值。全量补全是异步操作，应在配置保存后 fire-and-forget 触发。

### Step 3: Commit

```bash
git add backend/src/module/api/config.py backend/src/test/test_dandanplay_batch_trigger.py
git commit -m "feat: trigger batch dandanplay update on rename_method switch"
```
