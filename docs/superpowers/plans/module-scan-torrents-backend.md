# Scan Torrents 后端实现计划

**目标:** 实现"扫描种子"功能的后端部分，包括新增 Pydantic 模型、RSSEngine 的 `scan_bangumi_torrents()` 方法、以及两个新的 API 端点。

**规格文档:** `docs/superpowers/specs/2026-04-05-bangumi-scan-torrents-design.md`

**文件:**
- 修改: `backend/src/module/models/torrent.py` (第 51 行末尾追加)
- 修改: `backend/src/module/models/__init__.py` (第 6-13 行)
- 修改: `backend/src/module/rss/engine.py` (新增方法)
- 修改: `backend/src/module/api/bangumi.py` (新增端点)
- 新增: `backend/src/test/test_scan_torrents.py`

**依赖:**
- 已有: `module/rss/match_report.py` 中的 `MatchResult`
- 已有: `module/rss/engine.py` 中的 `match_torrent_with_details()`
- 已有: `module/network/request_contents.py` 中的 `RequestContent.get_torrents()`

---

## Task 1: 新增 Pydantic 模型

在 `torrent.py` 中新增 `ScannedTorrent`、`ScanTorrentsResponse`、`RecollectByUrlsRequest` 三个 Pydantic BaseModel，用于 scan-torrents 和 recollect-by-urls 端点的请求/响应体。同时在 `__init__.py` 中导出。

### 文件

- 修改: `backend/src/module/models/torrent.py` (第 53 行之后追加)
- 修改: `backend/src/module/models/__init__.py` (第 6-13 行)
- 新增: `backend/src/test/test_scan_torrents.py`

### 步骤

- [ ] **Step 1: 写测试**

在 `backend/src/test/test_scan_torrents.py` 中：

```python
"""Scan Torrents 功能测试。

覆盖模型定义、RSSEngine.scan_bangumi_torrents()、scan-torrents 端点、
recollect-by-urls 端点。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from module.api import v1
from module.models import Bangumi, Torrent
from module.models.torrent import (
    ScannedTorrent,
    ScanTorrentsResponse,
    RecollectByUrlsRequest,
)
from module.security.api import get_current_user

from test.factories import make_bangumi, make_torrent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """Create a FastAPI app with v1 routes for testing."""
    app = FastAPI()
    app.include_router(v1, prefix="/api")
    return app


@pytest.fixture
def authed_client(app):
    """TestClient with auth dependency overridden."""
    async def mock_user():
        return "testuser"

    app.dependency_overrides[get_current_user] = mock_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def unauthed_client(app):
    """TestClient without auth (no override)."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Task 1: 模型定义测试
# ---------------------------------------------------------------------------


class TestScannedTorrentModel:
    """ScannedTorrent Pydantic 模型测试。"""

    def test_full_fields(self):
        """所有字段都填写时正确构造。"""
        t = ScannedTorrent(
            name="[Group] Anime - 01 [1080p].mkv",
            url="https://example.com/anime-01.torrent",
            download_action="downloaded",
            matched_pattern="Anime",
            pattern_type="title_raw",
            filter_reason=None,
        )
        assert t.name == "[Group] Anime - 01 [1080p].mkv"
        assert t.url == "https://example.com/anime-01.torrent"
        assert t.download_action == "downloaded"
        assert t.matched_pattern == "Anime"
        assert t.pattern_type == "title_raw"
        assert t.filter_reason is None

    def test_minimal_fields(self):
        """仅必填字段时，可选字段默认 None。"""
        t = ScannedTorrent(
            name="[Group] Anime - 01 [720p].mkv",
            url="https://example.com/anime-01.torrent",
            download_action="filtered",
        )
        assert t.matched_pattern is None
        assert t.pattern_type is None
        assert t.filter_reason is None

    def test_filtered_with_reason(self):
        """filtered 状态附带过滤原因。"""
        t = ScannedTorrent(
            name="[Group] Anime - 01 [720p].mkv",
            url="https://example.com/anime-01.torrent",
            download_action="filtered",
            matched_pattern="Anime",
            pattern_type="title_raw",
            filter_reason="种子名称匹配 filter 正则 /720/",
        )
        assert t.filter_reason is not None
        assert "720" in t.filter_reason


class TestScanTorrentsResponseModel:
    """ScanTorrentsResponse Pydantic 模型测试。"""

    def test_empty_response(self):
        """空种子列表 + 报告。"""
        resp = ScanTorrentsResponse(
            report="RSS 中无匹配当前番剧的种子",
            torrents=[],
        )
        assert len(resp.torrents) == 0
        assert "无匹配" in resp.report

    def test_with_torrents(self):
        """包含多个种子的响应。"""
        resp = ScanTorrentsResponse(
            report="[下载] 2 个",
            torrents=[
                ScannedTorrent(
                    name="A",
                    url="https://a.com",
                    download_action="downloaded",
                ),
                ScannedTorrent(
                    name="B",
                    url="https://b.com",
                    download_action="filtered",
                    filter_reason="被过滤",
                ),
            ],
        )
        assert len(resp.torrents) == 2


class TestRecollectByUrlsRequestModel:
    """RecollectByUrlsRequest Pydantic 模型测试。"""

    def test_normal_urls(self):
        """正常 URL 列表。"""
        req = RecollectByUrlsRequest(
            torrent_urls=[
                "https://example.com/a.torrent",
                "https://example.com/b.torrent",
            ]
        )
        assert len(req.torrent_urls) == 2

    def test_empty_urls(self):
        """空 URL 列表（端点层应该拒绝，但模型本身允许）。"""
        req = RecollectByUrlsRequest(torrent_urls=[])
        assert len(req.torrent_urls) == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest src/test/test_scan_torrents.py::TestScannedTorrentModel -v`

预期：`ImportError: cannot import name 'ScannedTorrent' from 'module.models.torrent'`

- [ ] **Step 3: 写最小实现**

在 `backend/src/module/models/torrent.py` 第 53 行（文件末尾）之后追加：

```python
class ScannedTorrent(BaseModel):
    """扫描结果中的单个种子信息。"""
    name: str
    url: str
    download_action: str  # "downloaded" | "filtered"
    matched_pattern: Optional[str] = None
    pattern_type: Optional[str] = None  # "title_raw" | "alias"
    filter_reason: Optional[str] = None


class ScanTorrentsResponse(BaseModel):
    """scan-torrents 端点的响应体。"""
    report: str
    torrents: list[ScannedTorrent]


class RecollectByUrlsRequest(BaseModel):
    """recollect-by-urls 端点的请求体。"""
    torrent_urls: list[str]
```

在 `backend/src/module/models/__init__.py` 中更新 import（第 6-13 行）：

```python
from .torrent import (
    EpisodeFile,
    RecollectByUrlsRequest,
    RecollectRequest,
    ScanTorrentsResponse,
    ScannedTorrent,
    SubtitleFile,
    Torrent,
    TorrentDetail,
    TorrentUpdate,
)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest src/test/test_scan_torrents.py::TestScannedTorrentModel src/test/test_scan_torrents.py::TestScanTorrentsResponseModel src/test/test_scan_torrents.py::TestRecollectByUrlsRequestModel -v`

预期：全部 6 个模型测试通过。

- [ ] **Step 5: 提交**

```bash
git add backend/src/module/models/torrent.py backend/src/module/models/__init__.py backend/src/test/test_scan_torrents.py
git commit -m "feat(models): add ScannedTorrent, ScanTorrentsResponse, RecollectByUrlsRequest models

Add Pydantic models for scan-torrents and recollect-by-urls API endpoints.
These models represent scan results with match details and filter reasons."
```

---

## Task 2: RSSEngine.scan_bangumi_torrents() 方法

在 `RSSEngine` 中新增 `scan_bangumi_torrents()` 方法。该方法实时从番剧的 RSS 源拉取种子，对每个种子执行匹配，返回匹配到当前番剧的种子列表和简单报告文本。不写数据库。

关键设计：
- 不传 filter 参数给 `get_torrents()`，获取所有原始种子
- 调 `match_torrent_with_details()` 匹配所有番剧
- 按 `torrent.bangumi_id == bangumi_id` 过滤（int 比较，非字符串）
- 支持逗号分隔的多个 RSS URL
- 构建简单报告文本，不走 `MatchCollector.generate_report`

### 文件

- 修改: `backend/src/module/rss/engine.py` (新增 `scan_bangumi_torrents` 方法)
- 修改: `backend/src/test/test_scan_torrents.py` (追加测试)

### 步骤

- [ ] **Step 1: 写测试**

在 `backend/src/test/test_scan_torrents.py` 中追加：

```python
# ---------------------------------------------------------------------------
# Task 2: scan_bangumi_torrents 测试
# ---------------------------------------------------------------------------


class TestScanBangumiTorrents:
    """RSSEngine.scan_bangumi_torrents() 方法测试。"""

    def _make_mock_engine(self):
        """创建 mock 的 RSSEngine，注入必要依赖。"""
        with patch("module.rss.engine.Database.__init__", return_value=None):
            from module.rss.engine import RSSEngine

            engine = RSSEngine.__new__(RSSEngine)
            engine._filter_cache = {}
            engine.bangumi = MagicMock()
            return engine

    @pytest.mark.asyncio
    async def test_normal_match_downloaded(self):
        """匹配成功且未被 filter 过滤的种子返回 downloaded。"""
        engine = self._make_mock_engine()

        bangumi = make_bangumi(id=10, title_raw="TestAnime", filter="")
        engine.bangumi.search_id.return_value = bangumi

        torrent = Torrent(
            name="[Group] TestAnime - 01 [1080p].mkv",
            url="https://example.com/ep01.torrent",
        )

        # match_torrent_with_details 在匹配成功时会设置 torrent.bangumi_id
        def mock_match(t):
            t.bangumi_id = 10
            return bangumi, MagicMock(
                torrent_name=t.name,
                matched_bangumi="TestAnime (S1)",
                download_action="downloaded",
                matched_pattern="TestAnime",
                pattern_type="title_raw",
                filter_reason=None,
            )

        engine.match_torrent_with_details = mock_match

        with patch(
            "module.rss.engine.RequestContent"
        ) as MockReq:
            mock_instance = AsyncMock()
            mock_instance.get_torrents = AsyncMock(return_value=[torrent])
            MockReq.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockReq.return_value.__aexit__ = AsyncMock(return_value=False)

            results, report = await engine.scan_bangumi_torrents(10)

        assert len(results) == 1
        assert results[0].download_action == "downloaded"
        assert results[0].name == "[Group] TestAnime - 01 [1080p].mkv"

    @pytest.mark.asyncio
    async def test_filtered_torrent_included(self):
        """被 filter 过滤的种子也应出现在结果中（download_action="filtered"）。"""
        engine = self._make_mock_engine()

        bangumi = make_bangumi(id=10, title_raw="TestAnime", filter="720")
        engine.bangumi.search_id.return_value = bangumi

        torrent = Torrent(
            name="[Group] TestAnime - 01 [720p].mkv",
            url="https://example.com/ep01.torrent",
        )

        def mock_match(t):
            # filter 匹配到 720p，返回 filtered
            return None, MagicMock(
                torrent_name=t.name,
                matched_bangumi="TestAnime (S1)",
                download_action="filtered",
                matched_pattern="TestAnime",
                pattern_type="title_raw",
                filter_reason="种子名称匹配 filter 正则 /720/",
            )

        engine.match_torrent_with_details = mock_match

        with patch(
            "module.rss.engine.RequestContent"
        ) as MockReq:
            mock_instance = AsyncMock()
            mock_instance.get_torrents = AsyncMock(return_value=[torrent])
            MockReq.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockReq.return_value.__aexit__ = AsyncMock(return_value=False)

            results, report = await engine.scan_bangumi_torrents(10)

        assert len(results) == 1
        assert results[0].download_action == "filtered"
        assert "720" in results[0].filter_reason

    @pytest.mark.asyncio
    async def test_unmatched_torrent_excluded(self):
        """未匹配到当前番剧的种子不出现在结果中。"""
        engine = self._make_mock_engine()

        bangumi = make_bangumi(id=10, title_raw="TestAnime", filter="")
        engine.bangumi.search_id.return_value = bangumi

        # 这个种子匹配到了另一部番剧 (id=20)
        other_bangumi = make_bangumi(id=20, title_raw="OtherAnime")
        torrent = Torrent(
            name="[Group] OtherAnime - 01 [1080p].mkv",
            url="https://example.com/other.torrent",
        )

        def mock_match(t):
            t.bangumi_id = 20  # 匹配到另一部番剧
            return other_bangumi, MagicMock(
                torrent_name=t.name,
                matched_bangumi="OtherAnime",
                download_action="downloaded",
                matched_pattern="OtherAnime",
                pattern_type="title_raw",
                filter_reason=None,
            )

        engine.match_torrent_with_details = mock_match

        with patch(
            "module.rss.engine.RequestContent"
        ) as MockReq:
            mock_instance = AsyncMock()
            mock_instance.get_torrents = AsyncMock(return_value=[torrent])
            MockReq.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockReq.return_value.__aexit__ = AsyncMock(return_value=False)

            results, report = await engine.scan_bangumi_torrents(10)

        assert len(results) == 0
        assert "无匹配" in report

    @pytest.mark.asyncio
    async def test_bangumi_not_found(self):
        """bangumi_id 不存在时返回空列表 + 提示。"""
        engine = self._make_mock_engine()
        engine.bangumi.search_id.return_value = None

        results, report = await engine.scan_bangumi_torrents(999)

        assert len(results) == 0
        assert "未找到" in report

    @pytest.mark.asyncio
    async def test_empty_rss_link(self):
        """rss_link 为空时返回空列表 + 提示。"""
        engine = self._make_mock_engine()

        bangumi = make_bangumi(id=10, rss_link="")
        engine.bangumi.search_id.return_value = bangumi

        results, report = await engine.scan_bangumi_torrents(10)

        assert len(results) == 0
        assert "未配置 RSS" in report

    @pytest.mark.asyncio
    async def test_rss_fetch_error(self):
        """RSS 拉取失败时返回空列表 + 错误信息。"""
        engine = self._make_mock_engine()

        bangumi = make_bangumi(id=10, rss_link="https://example.com/rss")
        engine.bangumi.search_id.return_value = bangumi
        engine.match_torrent_with_details = MagicMock(
            return_value=(None, MagicMock(download_action="not_matched"))
        )

        with patch(
            "module.rss.engine.RequestContent"
        ) as MockReq:
            mock_instance = AsyncMock()
            mock_instance.get_torrents = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            MockReq.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockReq.return_value.__aexit__ = AsyncMock(return_value=False)

            results, report = await engine.scan_bangumi_torrents(10)

        assert len(results) == 0
        assert "Connection refused" in report

    @pytest.mark.asyncio
    async def test_multiple_rss_links(self):
        """逗号分隔的多个 RSS URL 逐个拉取并合并结果。"""
        engine = self._make_mock_engine()

        bangumi = make_bangumi(
            id=10,
            rss_link="https://rss1.com/feed,https://rss2.com/feed",
        )
        engine.bangumi.search_id.return_value = bangumi

        t1 = Torrent(name="[G] TestAnime - 01", url="https://a.com/1")
        t2 = Torrent(name="[G] TestAnime - 02", url="https://b.com/2")

        call_count = 0

        def mock_match(t):
            nonlocal call_count
            call_count += 1
            t.bangumi_id = 10
            return bangumi, MagicMock(
                torrent_name=t.name,
                matched_bangumi="TestAnime",
                download_action="downloaded",
                matched_pattern="TestAnime",
                pattern_type="title_raw",
                filter_reason=None,
            )

        engine.match_torrent_with_details = mock_match

        with patch(
            "module.rss.engine.RequestContent"
        ) as MockReq:
            mock_instance = AsyncMock()
            # 第一次调用返回 t1，第二次返回 t2
            mock_instance.get_torrents = AsyncMock(
                side_effect=[[t1], [t2]]
            )
            MockReq.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockReq.return_value.__aexit__ = AsyncMock(return_value=False)

            results, report = await engine.scan_bangumi_torrents(10)

        assert len(results) == 2
        assert mock_instance.get_torrents.call_count == 2

    @pytest.mark.asyncio
    async def test_report_text_format(self):
        """报告文本按 downloaded/filtered 分组列出种子名。"""
        engine = self._make_mock_engine()

        bangumi = make_bangumi(id=10, title_raw="TestAnime", filter="")
        engine.bangumi.search_id.return_value = bangumi

        t1 = Torrent(name="[G] TestAnime - 01 [1080p]", url="https://a.com/1")
        t2 = Torrent(name="[G] TestAnime - 02 [720p]", url="https://a.com/2")

        def mock_match(t):
            if "720p" in t.name:
                # 模拟被过滤
                return None, MagicMock(
                    torrent_name=t.name,
                    matched_bangumi="TestAnime",
                    download_action="filtered",
                    matched_pattern="TestAnime",
                    pattern_type="title_raw",
                    filter_reason="包含 720p",
                )
            t.bangumi_id = 10
            return bangumi, MagicMock(
                torrent_name=t.name,
                matched_bangumi="TestAnime",
                download_action="downloaded",
                matched_pattern="TestAnime",
                pattern_type="title_raw",
                filter_reason=None,
            )

        engine.match_torrent_with_details = mock_match

        with patch(
            "module.rss.engine.RequestContent"
        ) as MockReq:
            mock_instance = AsyncMock()
            mock_instance.get_torrents = AsyncMock(return_value=[t1, t2])
            MockReq.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            MockReq.return_value.__aexit__ = AsyncMock(return_value=False)

            results, report = await engine.scan_bangumi_torrents(10)

        # 报告中应包含 downloaded 和 filtered 两个分组
        assert "下载" in report
        assert "过滤" in report
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest src/test/test_scan_torrents.py::TestScanBangumiTorrents -v`

预期：`AttributeError: 'RSSEngine' object has no attribute 'scan_bangumi_torrents'`

- [ ] **Step 3: 写最小实现**

在 `backend/src/module/rss/engine.py` 中，在 `download_bangumi` 方法（文件末尾）之后追加：

**文件顶部新增 import（第 9 行 `from module.network import RequestContent` 之后）：**

```python
from module.models.torrent import ScannedTorrent
```

**在文件末尾追加方法：**

```python
    async def scan_bangumi_torrents(
        self, bangumi_id: int
    ) -> tuple[list[ScannedTorrent], str]:
        """实时从 RSS 拉取种子，匹配当前番剧，返回详情和报告。

        不传 filter 参数给 get_torrents()，获取所有原始种子。
        对每个种子调 match_torrent_with_details() 匹配所有番剧，
        只保留 bangumi_id 匹配当前番剧的种子。
        不写数据库。

        Returns:
            (ScannedTorrent 列表, 报告文本)
        """
        bangumi = self.bangumi.search_id(bangumi_id)
        if not bangumi:
            return [], f"未找到番组 id={bangumi_id}"

        if not bangumi.rss_link:
            return [], "未配置 RSS 链接"

        # 解析逗号分隔的多个 RSS URL
        rss_urls = [url.strip() for url in bangumi.rss_link.split(",") if url.strip()]

        # 逐个拉取并合并所有种子
        all_raw_torrents: list[Torrent] = []
        for rss_url in rss_urls:
            try:
                async with RequestContent() as req:
                    # 不传 filter，获取所有原始种子
                    torrents = await req.get_torrents(rss_url)
                    all_raw_torrents.extend(torrents)
            except Exception as e:
                logger.warning(
                    f"[Engine] scan_bangumi_torrents: 拉取 RSS 失败 {rss_url}: {e}"
                )
                return [], f"RSS 拉取失败: {e}"

        # 按 URL 去重（多个 RSS 源可能包含相同种子）
        seen_urls: set[str] = set()
        unique_torrents: list[Torrent] = []
        for t in all_raw_torrents:
            if t.url not in seen_urls:
                seen_urls.add(t.url)
                unique_torrents.append(t)

        # 对每个种子执行匹配
        scanned: list[ScannedTorrent] = []
        for torrent in unique_torrents:
            matched_bangumi, match_result = self.match_torrent_with_details(torrent)

            # 只保留匹配到当前番剧的种子
            if torrent.bangumi_id == bangumi_id:
                scanned.append(
                    ScannedTorrent(
                        name=torrent.name,
                        url=torrent.url,
                        download_action=match_result.download_action,
                        matched_pattern=match_result.matched_pattern,
                        pattern_type=match_result.pattern_type,
                        filter_reason=match_result.filter_reason,
                    )
                )

        # 构建简单报告文本
        report = self._build_scan_report(bangumi.official_title, scanned)
        return scanned, report

    @staticmethod
    def _build_scan_report(
        official_title: str, scanned: list[ScannedTorrent]
    ) -> str:
        """构建扫描报告文本。

        按 downloaded/filtered 分组列出种子名，适合在 UI 中展示。
        """
        if not scanned:
            return f"RSS 中无匹配「{official_title}」的种子"

        lines = [f"扫描「{official_title}」结果:"]

        downloaded = [t for t in scanned if t.download_action == "downloaded"]
        filtered = [t for t in scanned if t.download_action == "filtered"]

        if downloaded:
            lines.append(f"\n[下载] 符合下载条件 ({len(downloaded)} 个):")
            for t in downloaded:
                lines.append(f"  + {t.name}")
                if t.matched_pattern:
                    lines.append(
                        f"    匹配: {t.pattern_type or 'pattern'}=\"{t.matched_pattern}\""
                    )

        if filtered:
            lines.append(f"\n[过滤] 匹配但被过滤 ({len(filtered)} 个):")
            for t in filtered:
                lines.append(f"  - {t.name}")
                if t.filter_reason:
                    lines.append(f"    原因: {t.filter_reason}")

        return "\n".join(lines)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest src/test/test_scan_torrents.py::TestScanBangumiTorrents -v`

预期：全部 9 个测试通过。

- [ ] **Step 5: 提交**

```bash
git add backend/src/module/rss/engine.py backend/src/test/test_scan_torrents.py
git commit -m "feat(engine): add scan_bangumi_torrents() for real-time RSS scanning

Add RSSEngine.scan_bangumi_torrents() that fetches torrents from a bangumi's
RSS feed without applying filters, matches each torrent using
match_torrent_with_details(), and returns only torrents matching the target
bangumi. Supports comma-separated RSS URLs and URL deduplication."
```

---

## Task 3: POST /{bangumi_id}/scan-torrents API 端点

新增 `POST /api/v1/bangumi/{bangumi_id}/scan-torrents` 端点。需要认证。调用 `RSSEngine.scan_bangumi_torrents()` 返回扫描结果。

### 文件

- 修改: `backend/src/module/api/bangumi.py` (第 10 行 import，第 539 行之后追加端点)
- 修改: `backend/src/test/test_scan_torrents.py` (追加测试)

### 步骤

- [ ] **Step 1: 写测试**

在 `backend/src/test/test_scan_torrents.py` 中追加：

```python
# ---------------------------------------------------------------------------
# Task 3: scan-torrents API 端点测试
# ---------------------------------------------------------------------------


class TestScanTorrentsEndpoint:
    """POST /api/v1/bangumi/{bangumi_id}/scan-torrents 端点测试。"""

    def test_scan_torrents_success(self, authed_client):
        """正常扫描返回 ScanTorrentsResponse。"""
        scanned = [
            ScannedTorrent(
                name="[G] Anime - 01 [1080p]",
                url="https://a.com/1.torrent",
                download_action="downloaded",
                matched_pattern="Anime",
                pattern_type="title_raw",
            ),
        ]
        report = "扫描「Anime」结果:\n\n[下载] 符合下载条件 (1 个):\n  + [G] Anime - 01 [1080p]"

        with patch("module.api.bangumi.RSSEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.scan_bangumi_torrents = AsyncMock(
                return_value=(scanned, report)
            )
            # RSSEngine 继承 Database，需要 mock __init__ 和上下文管理器
            MockEngine.return_value.__init__ = MagicMock(return_value=None)
            MockEngine.return_value.__enter__ = MagicMock(return_value=mock_engine)
            MockEngine.return_value.__exit__ = MagicMock(return_value=False)

            # 需要让构造后的实例具有 scan_bangumi_torrents
            mock_instance = MagicMock()
            mock_instance.scan_bangumi_torrents = AsyncMock(
                return_value=(scanned, report)
            )
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            MockEngine.return_value = mock_instance

            response = authed_client.post("/api/v1/bangumi/1/scan-torrents")

        assert response.status_code == 200
        data = response.json()
        assert "report" in data
        assert "torrents" in data
        assert len(data["torrents"]) == 1
        assert data["torrents"][0]["download_action"] == "downloaded"

    def test_scan_torrents_empty_result(self, authed_client):
        """无匹配种子时返回空列表。"""
        with patch("module.api.bangumi.RSSEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.scan_bangumi_torrents = AsyncMock(
                return_value=([], "RSS 中无匹配「Anime」的种子")
            )
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            MockEngine.return_value = mock_instance

            response = authed_client.post("/api/v1/bangumi/999/scan-torrents")

        assert response.status_code == 200
        data = response.json()
        assert data["torrents"] == []

    def test_scan_torrents_auth_required(self, unauthed_client):
        """未认证请求返回 401。"""
        with patch("module.security.api.DEV_AUTH_BYPASS", False):
            response = unauthed_client.post("/api/v1/bangumi/1/scan-torrents")
        assert response.status_code == 401
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest src/test/test_scan_torrents.py::TestScanTorrentsEndpoint -v`

预期：`404 Not Found` 或路由不匹配（端点尚未注册）。

- [ ] **Step 3: 写最小实现**

在 `backend/src/module/api/bangumi.py` 中：

**更新 import（第 10 行），新增 RSSEngine 和 scan 相关模型：**

```python
from module.models import APIResponse, Bangumi, BangumiUpdate, TorrentDetail, RecollectRequest, Torrent
from module.models.torrent import ScanTorrentsResponse, RecollectByUrlsRequest
from module.rss.engine import RSSEngine
```

**在文件末尾（第 539 行之后）追加端点：**

```python
@router.post(
    path="/{bangumi_id}/scan-torrents",
    response_model=ScanTorrentsResponse,
    dependencies=[Depends(get_current_user)],
)
async def scan_torrents(bangumi_id: int):
    """实时从 RSS 拉取种子，匹配当前番剧，返回详情。不写入数据库。"""
    with RSSEngine() as engine:
        scanned, report = await engine.scan_bangumi_torrents(bangumi_id)

    return ScanTorrentsResponse(report=report, torrents=scanned)
```

**注意：** `RSSEngine` 继承自 `Database`，`Database` 继承自 `Session`。`Session` 本身不是上下文管理器，但 `Database` 在代码中被 `with Database() as db:` 这样使用（见 `bangumi.py` 第 320 行的 `dismiss_review` 端点）。这意味着 `Database`（以及 `RSSEngine`）支持上下文管理器模式。不过需要确认这一点。

查看 `backend/src/module/api/bangumi.py` 中已有的用法（第 320 行）：

```python
with Database() as db:
    success = db.bangumi.clear_needs_review(bangumi_id)
```

以及（第 399 行）：

```python
with Database() as db:
    torrents = db.torrent.search_by_bangumi_id(bangumi_id)
```

所以 `Database` 已经支持 `with` 语句。`RSSEngine` 继承自 `Database`，同样支持。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest src/test/test_scan_torrents.py::TestScanTorrentsEndpoint -v`

预期：全部 3 个测试通过。

- [ ] **Step 5: 提交**

```bash
git add backend/src/module/api/bangumi.py backend/src/test/test_scan_torrents.py
git commit -m "feat(api): add POST /bangumi/{id}/scan-torrents endpoint

Add scan-torrents endpoint that creates an RSSEngine, calls
scan_bangumi_torrents(), and returns ScanTorrentsResponse with
match details and report. Requires authentication."
```

---

## Task 4: POST /{bangumi_id}/recollect-by-urls API 端点

新增 `POST /api/v1/bangumi/{bangumi_id}/recollect-by-urls` 端点。接收 URL 列表，重新拉取 RSS 获取完整种子数据，写入 torrent 表并提交下载。

关键设计：
- 调 `engine.scan_bangumi_torrents(bangumi_id)` 重新获取种子
- 按 URL 过滤出请求的种子
- 对过滤出的种子设置 `torrent.bangumi_id = bangumi.id`
- 静默忽略不存在的 URL（RSS 可能已更新）
- 写入 torrent 表
- 提交下载客户端
- 更新 `downloaded = True`

### 文件

- 修改: `backend/src/module/api/bangumi.py` (追加端点)
- 修改: `backend/src/test/test_scan_torrents.py` (追加测试)

### 步骤

- [ ] **Step 1: 写测试**

在 `backend/src/test/test_scan_torrents.py` 中追加：

```python
# ---------------------------------------------------------------------------
# Task 4: recollect-by-urls API 端点测试
# ---------------------------------------------------------------------------


class TestRecollectByUrlsEndpoint:
    """POST /api/v1/bangumi/{bangumi_id}/recollect-by-urls 端点测试。"""

    def test_recollect_success(self, authed_client):
        """正常提交下载。"""
        # scan_bangumi_torrents 返回原始 Torrent 对象（通过 scan 的中间过程）
        # recollect-by-urls 端点内部调 scan_bangumi_torrents 获取种子列表
        # 然后按 URL 过滤

        # 构造 scan 返回的 ScannedTorrent
        scanned = [
            ScannedTorrent(
                name="[G] Anime - 01",
                url="https://a.com/1.torrent",
                download_action="downloaded",
            ),
            ScannedTorrent(
                name="[G] Anime - 02",
                url="https://a.com/2.torrent",
                download_action="downloaded",
            ),
        ]

        with patch("module.api.bangumi.RSSEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.scan_bangumi_torrents = AsyncMock(
                return_value=(scanned, "报告")
            )
            mock_engine.bangumi = MagicMock()
            mock_engine.bangumi.search_id.return_value = make_bangumi(id=1)
            mock_engine.torrent = MagicMock()
            mock_engine.__enter__ = MagicMock(return_value=mock_engine)
            mock_engine.__exit__ = MagicMock(return_value=False)
            MockEngine.return_value = mock_engine

            with patch("module.api.bangumi.DownloadClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.add_torrent = AsyncMock(return_value=True)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                response = authed_client.post(
                    "/api/v1/bangumi/1/recollect-by-urls",
                    json={
                        "torrent_urls": [
                            "https://a.com/1.torrent",
                        ]
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] is True

    def test_recollect_silently_ignores_missing_urls(self, authed_client):
        """请求的 URL 不在扫描结果中时静默忽略。"""
        scanned = [
            ScannedTorrent(
                name="[G] Anime - 01",
                url="https://a.com/1.torrent",
                download_action="downloaded",
            ),
        ]

        with patch("module.api.bangumi.RSSEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.scan_bangumi_torrents = AsyncMock(
                return_value=(scanned, "报告")
            )
            mock_engine.bangumi = MagicMock()
            mock_engine.bangumi.search_id.return_value = make_bangumi(id=1)
            mock_engine.torrent = MagicMock()
            mock_engine.__enter__ = MagicMock(return_value=mock_engine)
            mock_engine.__exit__ = MagicMock(return_value=False)
            MockEngine.return_value = mock_engine

            with patch("module.api.bangumi.DownloadClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.add_torrent = AsyncMock(return_value=True)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                response = authed_client.post(
                    "/api/v1/bangumi/1/recollect-by-urls",
                    json={
                        "torrent_urls": [
                            "https://a.com/1.torrent",
                            "https://nonexistent.com/gone.torrent",
                        ]
                    },
                )

        assert response.status_code == 200
        # 只有 1 个种子被实际处理
        mock_engine.torrent.add_all.assert_called_once()
        added_torrents = mock_engine.torrent.add_all.call_args[0][0]
        assert len(added_torrents) == 1
        assert added_torrents[0].url == "https://a.com/1.torrent"

    def test_recollect_bangumi_not_found(self, authed_client):
        """番剧不存在时返回 404。"""
        with patch("module.api.bangumi.RSSEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.scan_bangumi_torrents = AsyncMock(
                return_value=([], "未找到番组 id=999")
            )
            mock_engine.bangumi = MagicMock()
            mock_engine.bangumi.search_id.return_value = None
            mock_engine.__enter__ = MagicMock(return_value=mock_engine)
            mock_engine.__exit__ = MagicMock(return_value=False)
            MockEngine.return_value = mock_engine

            response = authed_client.post(
                "/api/v1/bangumi/999/recollect-by-urls",
                json={
                    "torrent_urls": ["https://a.com/1.torrent"]
                },
            )

        assert response.status_code == 404

    def test_recollect_no_matching_urls(self, authed_client):
        """所有请求的 URL 都不在扫描结果中时返回错误。"""
        scanned = [
            ScannedTorrent(
                name="[G] Anime - 01",
                url="https://a.com/1.torrent",
                download_action="downloaded",
            ),
        ]

        with patch("module.api.bangumi.RSSEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.scan_bangumi_torrents = AsyncMock(
                return_value=(scanned, "报告")
            )
            mock_engine.bangumi = MagicMock()
            mock_engine.bangumi.search_id.return_value = make_bangumi(id=1)
            mock_engine.torrent = MagicMock()
            mock_engine.__enter__ = MagicMock(return_value=mock_engine)
            mock_engine.__exit__ = MagicMock(return_value=False)
            MockEngine.return_value = mock_engine

            response = authed_client.post(
                "/api/v1/bangumi/1/recollect-by-urls",
                json={
                    "torrent_urls": [
                        "https://totally-different.com/missing.torrent",
                    ]
                },
            )

        assert response.status_code == 400

    def test_recollect_auth_required(self, unauthed_client):
        """未认证请求返回 401。"""
        with patch("module.security.api.DEV_AUTH_BYPASS", False):
            response = unauthed_client.post(
                "/api/v1/bangumi/1/recollect-by-urls",
                json={"torrent_urls": ["https://a.com/1.torrent"]},
            )
        assert response.status_code == 401

    def test_recollect_download_client_failure(self, authed_client):
        """下载客户端添加失败时返回 500。"""
        scanned = [
            ScannedTorrent(
                name="[G] Anime - 01",
                url="https://a.com/1.torrent",
                download_action="downloaded",
            ),
        ]

        with patch("module.api.bangumi.RSSEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.scan_bangumi_torrents = AsyncMock(
                return_value=(scanned, "报告")
            )
            mock_engine.bangumi = MagicMock()
            mock_engine.bangumi.search_id.return_value = make_bangumi(id=1)
            mock_engine.torrent = MagicMock()
            mock_engine.__enter__ = MagicMock(return_value=mock_engine)
            mock_engine.__exit__ = MagicMock(return_value=False)
            MockEngine.return_value = mock_engine

            with patch("module.api.bangumi.DownloadClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.add_torrent = AsyncMock(return_value=False)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                response = authed_client.post(
                    "/api/v1/bangumi/1/recollect-by-urls",
                    json={
                        "torrent_urls": ["https://a.com/1.torrent"]
                    },
                )

        assert response.status_code == 500
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest src/test/test_scan_torrents.py::TestRecollectByUrlsEndpoint -v`

预期：`404 Not Found`（端点尚未注册）。

- [ ] **Step 3: 写最小实现**

在 `backend/src/module/api/bangumi.py` 中，在 scan-torrents 端点之后追加：

```python
@router.post(
    path="/{bangumi_id}/recollect-by-urls",
    response_model=APIResponse,
    dependencies=[Depends(get_current_user)],
)
async def recollect_by_urls(bangumi_id: int, request: RecollectByUrlsRequest):
    """按种子 URL 列表提交下载。重新拉取 RSS 获取种子完整数据。

    静默忽略不在当前 RSS 中的 URL（RSS 可能已更新）。
    """
    with RSSEngine() as engine:
        # 重新拉取 RSS 获取完整种子数据
        scanned, _ = await engine.scan_bangumi_torrents(bangumi_id)

        # 获取番剧信息
        bangumi = engine.bangumi.search_id(bangumi_id)
        if not bangumi:
            return JSONResponse(
                status_code=404,
                content={
                    "status": False,
                    "msg_en": f"Bangumi {bangumi_id} not found.",
                    "msg_zh": f"未找到番剧 {bangumi_id}。",
                },
            )

        # 按 URL 过滤出请求的种子
        url_set = set(request.torrent_urls)
        matched_scanned = [t for t in scanned if t.url in url_set]

        if not matched_scanned:
            return JSONResponse(
                status_code=400,
                content={
                    "status": False,
                    "msg_en": "No matching torrents found in current RSS feed.",
                    "msg_zh": "当前 RSS 中未找到匹配的种子。",
                },
            )

        # 从扫描结果重建 Torrent ORM 对象用于写入数据库和下载
        torrents = []
        for t in matched_scanned:
            torrent = Torrent(
                name=t.name,
                url=t.url,
                bangumi_id=bangumi_id,
                downloaded=False,
            )
            torrents.append(torrent)

        # 写入 torrent 表
        engine.torrent.add_all(torrents)

    # 提交下载客户端
    try:
        async with DownloadClient() as client:
            success = await client.add_torrent(torrents, bangumi)
            if not success:
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": False,
                        "msg_en": "Failed to add torrents to download client.",
                        "msg_zh": "添加种子到下载客户端失败。",
                    },
                )

        # 更新下载状态
        with RSSEngine() as engine:
            for t in torrents:
                t.downloaded = True
            engine.torrent.update_all(torrents)

    except Exception as e:
        logger.error("[API] Recollect-by-urls failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={
                "status": False,
                "msg_en": f"Recollect failed: {str(e)}",
                "msg_zh": f"重新收集失败: {str(e)}",
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": True,
            "msg_en": f"Successfully recollected {len(torrents)} torrents.",
            "msg_zh": f"成功重新收集 {len(torrents)} 个种子。",
        },
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest src/test/test_scan_torrents.py::TestRecollectByUrlsEndpoint -v`

预期：全部 6 个测试通过。

- [ ] **Step 5: 提交**

```bash
git add backend/src/module/api/bangumi.py backend/src/test/test_scan_torrents.py
git commit -m "feat(api): add POST /bangumi/{id}/recollect-by-urls endpoint

Add recollect-by-urls endpoint that re-fetches RSS to get full torrent data,
filters by requested URLs, writes to torrent table, and submits to download
client. Silently ignores URLs no longer in RSS feed."
```

---

## 最终验证

- [ ] **Step 1: 运行全部 scan-torrents 测试**

Run: `cd backend && uv run pytest src/test/test_scan_torrents.py -v`

预期：全部测试通过（模型: 6, scan_bangumi_torrents: 9, scan-torrents 端点: 3, recollect-by-urls 端点: 6 = 24 个测试）。

- [ ] **Step 2: 确认不影响现有测试**

Run: `cd backend && uv run pytest src/test/ -v --timeout=60`

预期：全部现有测试仍然通过。

- [ ] **Step 3: 如果有失败的现有测试，排查是否为本改动导致**

主要检查：
- `test_rss_engine_new.py` — RSSEngine 测试，需确认新方法不影响
- `test_engine_integration.py` — match_torrent_with_details 测试
- `test_api_bangumi.py` / `test_api_bangumi_extended.py` — bangumi API 测试

---

## 文件最终结构

```
backend/src/
├── module/
│   ├── api/
│   │   └── bangumi.py                      # 新增 scan-torrents, recollect-by-urls 端点
│   ├── models/
│   │   ├── __init__.py                      # 新增 ScannedTorrent 等导出
│   │   └── torrent.py                       # 新增 ScannedTorrent, ScanTorrentsResponse,
│   │                                        #   RecollectByUrlsRequest
│   └── rss/
│       └── engine.py                        # 新增 scan_bangumi_torrents(),
│                                            #   _build_scan_report()
└── test/
    └── test_scan_torrents.py                # 全部测试（24 个）
```

---

## 实现注意事项

1. **`get_torrents()` 不传 filter 参数**: `RequestContent.get_torrents(rss_url)` 默认 `_filter=None`，此时会使用全局默认 filter（`settings.rss_parser.filter`）过滤非视频文件，但不会应用番剧级别的排除规则。这确保 scan 能看到被番剧 filter 排除的种子。

2. **`torrent.bangumi_id == bangumi_id` 用 int 比较**: `match_torrent_with_details` 在匹配成功时设置 `torrent.bangumi_id = matched.id`（int 类型）。过滤时直接用 `==` 比较 int 值，不涉及字符串比较。

3. **recollect-by-urls 重建 Torrent 对象**: `scan_bangumi_torrents()` 返回的是 `ScannedTorrent`（Pydantic BaseModel），不是 `Torrent`（SQLModel ORM 对象）。recollect 端点需要从 `ScannedTorrent` 重建 `Torrent` ORM 对象才能写入数据库和提交下载。

4. **两个 RSSEngine 上下文**: recollect-by-urls 中使用了两个 `with RSSEngine() as engine:` 块——第一个用于 scan + 写入 torrent 表，第二个用于更新 downloaded 状态。这是因为 `DownloadClient` 也是异步上下文管理器，嵌套在 RSSEngine 内部时 session 管理可能冲突。两次独立创建 RSSEngine 更安全。

5. **路由注册顺序**: FastAPI 按注册顺序匹配路由。由于 `/{bangumi_id}/scan-torrents` 和 `/{bangumi_id}/recollect-by-urls` 是 POST 方法且有明确的 path suffix，不会与已有的 `/{bangumi_id}/torrents` (GET) 等端点冲突。但需要确保这两个端点注册在 `/{bangumi_id}/recollect` 之后（recollect 是 POST 方法，路径更短），避免被错误匹配。

6. **`_build_scan_report` 是静态方法**: 报告构建不需要实例状态，作为静态方法方便单独测试。报告格式简洁，按 downloaded/filtered 两组列出，与 `MatchCollector.generate_report` 的多 RSS 源格式不同，因为 scan 场景只有单部番剧。
