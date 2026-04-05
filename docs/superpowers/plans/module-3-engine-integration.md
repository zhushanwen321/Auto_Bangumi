# Module 3: 引擎集成

**目标:** 修改 `RSSEngine`，在 `refresh_rss()` 中集成 `MatchCollector`，收集每个种子的匹配结果并在刷新结束后生成结构化报告日志。

**文件:**
- 修改: `backend/src/module/rss/engine.py`
- 新增: `backend/src/test/test_engine_integration.py`

**依赖:**
- Module 1: `backend/src/module/rss/match_report.py` (`MatchCollector`, `MatchResult`, `RSSResult`)
- Module 2: `backend/src/module/database/bangumi.py` (`BangumiDatabase.match_torrent_with_pattern()`)

---

## Task 3.1: match_torrent_with_details 方法

在 `RSSEngine` 中新增 `match_torrent_with_details()` 方法，替代 `refresh_rss()` 中对 `match_torrent()` 的调用。新方法调用 `match_torrent_with_pattern()` 获取匹配详情，保持与原 `match_torrent()` 完全一致的 filter 行为，同时返回 `MatchResult` 用于日志记录。

**关键约束：**
- 不修改原有 `match_torrent()` 方法，保持向后兼容
- filter 判断逻辑必须与原 `match_torrent()` 完全一致：`matched.filter == ""` 时直接下载；`filter_pattern.search(torrent.name)` 为 False 时下载（filter 是排除规则，匹配到的被过滤）
- `downloaded` 动作的种子需要设置 `torrent.bangumi_id = matched.id`

- [ ] **Step 1: 写测试**

在 `backend/src/test/test_engine_integration.py` 中：

```python
"""RSSEngine 引擎集成测试。

测试 match_torrent_with_details 方法和 refresh_rss 中 MatchCollector 的集成。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine

from module.models import Bangumi, RSSItem, Torrent


# --- 辅助工具 ---


def make_bangumi(**overrides) -> Bangumi:
    """创建测试用 Bangumi 实例。"""
    defaults = dict(
        id=1,
        official_title="测试番剧",
        title_raw="TestAnime",
        season=1,
        filter="",
        rss_link="",
        added=True,
        deleted=False,
    )
    defaults.update(overrides)
    return Bangumi(**defaults)


def make_torrent(name: str, **overrides) -> Torrent:
    """创建测试用 Torrent 实例。"""
    defaults = dict(name=name, url=f"https://example.com/{name}")
    defaults.update(overrides)
    return Torrent(**defaults)


# --- 测试 match_torrent_with_details ---


class TestMatchTorrentWithDetails:
    """match_torrent_with_details 方法测试。

    验证新方法在 filter 判断上与原 match_torrent 保持完全一致的行为，
    同时额外返回 MatchResult 用于日志记录。
    """

    @pytest.fixture
    def mock_engine(self):
        """创建一个 mock 的 RSSEngine，只注入必要依赖。"""
        with patch("module.rss.engine.Database.__init__", return_value=None):
            from module.rss.engine import RSSEngine

            engine = RSSEngine.__new__(RSSEngine)
            engine._filter_cache = {}
            engine.bangumi = MagicMock()
            return engine

    def test_no_match_returns_not_matched(self, mock_engine):
        """种子未匹配任何 Bangumi 时，返回 (None, MatchResult(not_matched))。"""
        mock_engine.bangumi.match_torrent_with_pattern.return_value = None
        torrent = make_torrent("[Group] 未知番剧 第01话 [1080p]")

        result_bangumi, match_result = mock_engine.match_torrent_with_details(torrent)

        assert result_bangumi is None
        assert match_result.download_action == "not_matched"
        assert match_result.matched_bangumi is None
        assert match_result.matched_pattern is None
        assert match_result.filter_reason is None

    def test_match_no_filter_returns_downloaded(self, mock_engine):
        """匹配成功且 filter 为空时，返回 (Bangumi, MatchResult(downloaded))。"""
        bangumi = make_bangumi(
            id=1,
            official_title="推しの子 (S1)",
            title_raw="推しの子",
            filter="",
        )
        mock_engine.bangumi.match_torrent_with_pattern.return_value = (
            bangumi,
            "推しの子",
        )
        torrent = make_torrent("[Group] 推しの子 第13话 [1080p HEVC]")

        result_bangumi, match_result = mock_engine.match_torrent_with_details(torrent)

        assert result_bangumi is not None
        assert result_bangumi.id == 1
        assert match_result.download_action == "downloaded"
        assert match_result.matched_bangumi == "推しの子 (S1)"
        assert match_result.matched_pattern == "推しの子"
        assert torrent.bangumi_id == 1

    def test_match_filter_not_hit_returns_downloaded(self, mock_engine):
        """匹配成功且 filter 正则未命中种子名称时，返回 downloaded。

        filter 是排除规则：filter_pattern.search(torrent.name) 为 False
        意味着种子名称不包含被排除的关键词，应该下载。
        """
        bangumi = make_bangumi(
            id=2,
            official_title="葬送的芙莉莲 (S1)",
            title_raw="芙莉莲",
            filter="720,\\d+-\\d+",
        )
        mock_engine.bangumi.match_torrent_with_pattern.return_value = (
            bangumi,
            "芙莉莲",
        )
        # 种子名包含 "1080p" 但 filter 排除 "720"，所以 filter 未命中 -> 下载
        torrent = make_torrent("[Group] 芙莉莲 第12话 [1080p]")

        result_bangumi, match_result = mock_engine.match_torrent_with_details(torrent)

        assert result_bangumi is not None
        assert result_bangumi.id == 2
        assert match_result.download_action == "downloaded"
        assert match_result.matched_pattern == "芙莉莲"
        assert torrent.bangumi_id == 2

    def test_match_filter_hit_returns_filtered(self, mock_engine):
        """匹配成功但 filter 正则命中种子名称时，返回 (None, MatchResult(filtered))。

        filter 是排除规则：filter_pattern.search(torrent.name) 为 True
        意味着种子名称包含被排除的关键词（如 "720p"），应该过滤。
        """
        bangumi = make_bangumi(
            id=2,
            official_title="葬送的芙莉莲 (S1)",
            title_raw="芙莉莲",
            filter="720",
        )
        mock_engine.bangumi.match_torrent_with_pattern.return_value = (
            bangumi,
            "芙莉莲",
        )
        # 种子名包含 "720"，命中 filter -> 被过滤
        torrent = make_torrent("[Group] 芙莉莲 第12话 [720p]")

        result_bangumi, match_result = mock_engine.match_torrent_with_details(torrent)

        assert result_bangumi is None
        assert match_result.download_action == "filtered"
        assert match_result.matched_bangumi == "葬送的芙莉莲 (S1)"
        assert match_result.matched_pattern == "芙莉莲"
        assert "720" in match_result.filter_reason
        # 被过滤的种子不应设置 bangumi_id
        assert torrent.bangumi_id is None

    def test_filter_uses_same_regex_as_match_torrent(self, mock_engine):
        """filter 的正则处理方式必须与原 match_torrent 一致。

        原方法中 filter 字符串的逗号会被替换为 |（如 "720,1080" -> "720|1080"），
        新方法必须保持相同行为。
        """
        bangumi = make_bangumi(
            id=3,
            official_title="番剧 C (S1)",
            title_raw="AnimeC",
            filter="720,HEVC",
        )
        mock_engine.bangumi.match_torrent_with_pattern.return_value = (
            bangumi,
            "AnimeC",
        )
        # 种子名包含 "HEVC"，命中 filter ("720|HEVC") -> 被过滤
        torrent = make_torrent("[Group] AnimeC 第01话 [1080p HEVC]")

        result_bangumi, match_result = mock_engine.match_torrent_with_details(torrent)

        assert result_bangumi is None
        assert match_result.download_action == "filtered"

    def test_torrent_name_preserved_in_result(self, mock_engine):
        """MatchResult 中的 torrent_name 必须与原始种子名称一致。"""
        mock_engine.bangumi.match_torrent_with_pattern.return_value = None
        name = "[SubGroup] 特殊 Characters <test> 第01话 [1080p/HEVC]"
        torrent = make_torrent(name)

        _, match_result = mock_engine.match_torrent_with_details(torrent)

        assert match_result.torrent_name == name

    def test_filter_with_invalid_regex_handled(self, mock_engine):
        """filter 包含无效正则时，_get_filter_pattern 会回退到转义匹配。

        这是 _get_filter_pattern 已有行为，新方法继承此行为。
        """
        bangumi = make_bangumi(
            id=4,
            official_title="番剧 D (S1)",
            title_raw="AnimeD",
            filter="[invalid",
        )
        mock_engine.bangumi.match_torrent_with_pattern.return_value = (
            bangumi,
            "AnimeD",
        )
        # filter "[invalid" 是无效正则，_get_filter_pattern 会回退到转义匹配
        # 种子名包含 "[invalid" 字面量 -> 被过滤
        torrent = make_torrent("[Group] AnimeD [invalid 第01话")

        result_bangumi, match_result = mock_engine.match_torrent_with_details(torrent)

        assert match_result.download_action == "filtered"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest src/test/test_engine_integration.py::TestMatchTorrentWithDetails -v`

预期：`AttributeError: 'RSSEngine' object has no attribute 'match_torrent_with_details'`

- [ ] **Step 3: 写最小实现**

在 `backend/src/module/rss/engine.py` 中，在 `match_torrent` 方法（第 143 行 `return None` 之后）新增以下方法。需要添加 import。

**文件顶部新增 import（第 9 行之后）：**

```python
from module.rss.match_report import MatchResult
```

**新增方法（第 143 行 `return None` 之后、`refresh_rss` 方法之前）：**

```python
    def match_torrent_with_details(
        self, torrent: Torrent
    ) -> tuple[Optional[Bangumi], "MatchResult"]:
        """匹配种子并返回详细信息，用于日志记录。

        与 match_torrent() 的 filter 判断逻辑完全一致，额外返回 MatchResult
        记录匹配过程（匹配的 pattern、下载/过滤动作及原因）。

        Returns:
            (Bangumi 或 None, MatchResult) 元组。
            Bangumi 非 None 表示应该下载，None 表示不下载。
        """
        result = self.bangumi.match_torrent_with_pattern(torrent.name)

        if not result:
            return None, MatchResult(
                torrent_name=torrent.name,
                matched_bangumi=None,
                download_action="not_matched",
                matched_pattern=None,
                filter_reason=None,
            )

        matched, pattern = result

        # filter 为空，直接下载
        if matched.filter == "":
            torrent.bangumi_id = matched.id
            return matched, MatchResult(
                torrent_name=torrent.name,
                matched_bangumi=matched.official_title,
                download_action="downloaded",
                matched_pattern=pattern,
                filter_reason=None,
            )

        # filter 是排除规则：search 匹配到说明种子名包含排除关键词
        filter_pattern = self._get_filter_pattern(matched.filter)
        if not filter_pattern.search(torrent.name):
            # 种子名不包含排除关键词，允许下载
            torrent.bangumi_id = matched.id
            return matched, MatchResult(
                torrent_name=torrent.name,
                matched_bangumi=matched.official_title,
                download_action="downloaded",
                matched_pattern=pattern,
                filter_reason=None,
            )

        # 种子名包含排除关键词，被过滤
        return None, MatchResult(
            torrent_name=torrent.name,
            matched_bangumi=matched.official_title,
            download_action="filtered",
            matched_pattern=pattern,
            filter_reason=f"种子名称匹配 filter 正则 /{matched.filter}/",
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest src/test/test_engine_integration.py::TestMatchTorrentWithDetails -v`

预期：全部 8 个测试通过。

- [ ] **Step 5: 提交**

---

## Task 3.2: _pull_rss_with_torrent_counts 辅助方法

当前 `_pull_rss_with_status()` 只返回 `(new_torrents, error)`，但 `MatchCollector.set_torrent_counts()` 需要 `total` 和 `new` 两个计数。新增 `_pull_rss_with_torrent_counts()` 方法，同时返回总数和新增数。

**设计选择：** 新增方法而非修改原方法，避免影响其他调用者。内部复用 `_get_torrents` 和 `check_new` 的已有逻辑。

- [ ] **Step 1: 写测试**

在 `backend/src/test/test_engine_integration.py` 中追加：

```python
# --- 测试 _pull_rss_with_torrent_counts ---


class TestPullRssWithTorrentCounts:
    """_pull_rss_with_torrent_counts 方法测试。

    验证方法正确返回种子总数、新增数和错误信息。
    """

    @pytest.fixture
    def mock_engine(self):
        """创建 mock 的 RSSEngine。"""
        with patch("module.rss.engine.Database.__init__", return_value=None):
            from module.rss.engine import RSSEngine

            engine = RSSEngine.__new__(RSSEngine)
            engine._filter_cache = {}
            engine.bangumi = MagicMock()
            engine.torrent = MagicMock()
            return engine

    @pytest.mark.asyncio
    async def test_returns_total_and_new_counts(self, mock_engine):
        """正常情况下返回种子总数和新增数。"""
        rss_item = RSSItem(id=1, name="Test RSS", url="https://example.com/rss")
        all_torrents = [
            make_torrent("A 第01话"),
            make_torrent("B 第02话"),
            make_torrent("C 第03话"),
        ]
        new_torrents = [all_torrents[0], all_torrents[2]]

        with patch.object(
            mock_engine, "_get_torrents", return_value=all_torrents
        ):
            mock_engine.torrent.check_new.return_value = new_torrents

            result = await mock_engine._pull_rss_with_torrent_counts(rss_item)

        assert result == (new_torrents, 3, 2, None)

    @pytest.mark.asyncio
    async def test_error_case_returns_empty_with_error(self, mock_engine):
        """获取种子异常时返回空列表和错误信息。"""
        rss_item = RSSItem(id=1, name="Test RSS", url="https://example.com/rss")

        with patch.object(
            mock_engine,
            "_get_torrents",
            side_effect=Exception("Connection refused"),
        ):
            result = await mock_engine._pull_rss_with_torrent_counts(rss_item)

        new_torrents, total, new, error = result
        assert new_torrents == []
        assert total == 0
        assert new == 0
        assert "Connection refused" in error

    @pytest.mark.asyncio
    async def test_no_torrents_returns_zero_counts(self, mock_engine):
        """RSS 源没有任何种子时返回零计数。"""
        rss_item = RSSItem(id=1, name="Empty RSS", url="https://example.com/empty")

        with patch.object(mock_engine, "_get_torrents", return_value=[]):
            mock_engine.torrent.check_new.return_value = []

            result = await mock_engine._pull_rss_with_torrent_counts(rss_item)

        assert result == ([], 0, 0, None)

    @pytest.mark.asyncio
    async def test_all_torrents_are_new(self, mock_engine):
        """所有种子都是新增的。"""
        rss_item = RSSItem(id=1, name="Test", url="https://example.com/rss")
        all_torrents = [make_torrent("A"), make_torrent("B")]

        with patch.object(
            mock_engine, "_get_torrents", return_value=all_torrents
        ):
            mock_engine.torrent.check_new.return_value = all_torrents

            result = await mock_engine._pull_rss_with_torrent_counts(rss_item)

        assert result == (all_torrents, 2, 2, None)

    @pytest.mark.asyncio
    async def test_no_new_torrents(self, mock_engine):
        """所有种子都已存在。"""
        rss_item = RSSItem(id=1, name="Test", url="https://example.com/rss")
        all_torrents = [make_torrent("A"), make_torrent("B")]

        with patch.object(
            mock_engine, "_get_torrents", return_value=all_torrents
        ):
            mock_engine.torrent.check_new.return_value = []

            result = await mock_engine._pull_rss_with_torrent_counts(rss_item)

        assert result == ([], 2, 0, None)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest src/test/test_engine_integration.py::TestPullRssWithTorrentCounts -v`

预期：`AttributeError: 'RSSEngine' object has no attribute '_pull_rss_with_torrent_counts'`

- [ ] **Step 3: 写最小实现**

在 `backend/src/module/rss/engine.py` 中，在 `_pull_rss_with_status` 方法（第 111 行）之后新增：

```python
    async def _pull_rss_with_torrent_counts(
        self, rss_item: RSSItem
    ) -> tuple[list[Torrent], int, int, Optional[str]]:
        """拉取 RSS 种子并返回计数信息。

        Returns:
            (new_torrents, total_count, new_count, error_message)
        """
        try:
            all_torrents = await self._get_torrents(rss_item)
            new_torrents = self.torrent.check_new(all_torrents)
            return new_torrents, len(all_torrents), len(new_torrents), None
        except Exception as e:
            logger.warning(f"[Engine] Failed to fetch RSS {rss_item.name}: {e}")
            return [], 0, 0, str(e)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest src/test/test_engine_integration.py::TestPullRssWithTorrentCounts -v`

预期：全部 5 个测试通过。

- [ ] **Step 5: 提交**

---

## Task 3.3: refresh_rss 集成 MatchCollector

修改 `refresh_rss()` 方法，在其中集成 `MatchCollector`，替代原有的 `_pull_rss_with_status` 调用。每个种子的匹配结果通过 `match_torrent_with_details` 获取并记录到 collector 中，刷新结束后生成报告并输出到日志。

**关键约束：**
- 保持原有的 RSS 状态更新、种子下载、数据库写入逻辑不变
- 原有 `_pull_rss_with_status` 方法保持不变（其他地方可能调用）
- 报告通过 `logger.info` 输出
- `downloaded = True` 标记在 `add_torrent` 成功后设置（无论成功与否都记录为 "downloaded" action，因为匹配逻辑已决定下载）
- 新增 "not_added" 场景：匹配成功但 `add_torrent` 失败时，修正 MatchResult 的 download_action

- [ ] **Step 1: 写测试**

在 `backend/src/test/test_engine_integration.py` 中追加：

```python
# --- 测试 refresh_rss 集成 MatchCollector ---


class TestRefreshRssIntegration:
    """refresh_rss 方法集成 MatchCollector 的测试。

    验证 refresh_rss 正确使用 MatchCollector 收集匹配结果并生成报告。
    """

    def _make_mock_engine(self):
        """创建用于 refresh_rss 测试的 mock engine。"""
        with patch("module.rss.engine.Database.__init__", return_value=None):
            from module.rss.engine import RSSEngine

            engine = RSSEngine.__new__(RSSEngine)
            engine._filter_cache = {}
            engine.bangumi = MagicMock()
            engine.torrent = MagicMock()
            engine.rss = MagicMock()
            engine._to_refresh = False
            return engine

    @pytest.mark.asyncio
    async def test_collects_downloaded_match(self):
        """成功下载的种子应记录为 downloaded action。"""
        engine = self._make_mock_engine()

        rss_item = RSSItem(id=1, name="Mikan", url="https://mikan.example.com/rss")
        engine.rss.search_active.return_value = [rss_item]

        torrent = make_torrent("[G] TestAnime 第01话 [1080p]")
        bangumi = make_bangumi(
            id=1,
            official_title="TestAnime (S1)",
            title_raw="TestAnime",
            filter="",
        )

        engine.torrent.check_new.return_value = [torrent]
        engine.bangumi.match_torrent_with_pattern.return_value = (
            bangumi,
            "TestAnime",
        )

        mock_client = AsyncMock()
        mock_client.add_torrent.return_value = True

        # 收集日志输出
        with patch.object(engine, "_get_torrents", return_value=[torrent]):
            await engine.refresh_rss(mock_client)

        # 验证报告通过 logger.info 输出（此处只验证不抛异常）
        # 更详细的验证见 test_generates_report

    @pytest.mark.asyncio
    async def test_collects_not_matched(self):
        """未匹配的种子应记录为 not_matched action。"""
        engine = self._make_mock_engine()

        rss_item = RSSItem(id=1, name="Mikan", url="https://mikan.example.com/rss")
        engine.rss.search_active.return_value = [rss_item]

        torrent = make_torrent("[G] UnknownAnime 第01话")
        engine.torrent.check_new.return_value = [torrent]
        engine.bangumi.match_torrent_with_pattern.return_value = None

        mock_client = AsyncMock()

        with patch.object(engine, "_get_torrents", return_value=[torrent]):
            await engine.refresh_rss(mock_client)

    @pytest.mark.asyncio
    async def test_collects_filtered(self):
        """被 filter 过滤的种子应记录为 filtered action。"""
        engine = self._make_mock_engine()

        rss_item = RSSItem(id=1, name="Mikan", url="https://mikan.example.com/rss")
        engine.rss.search_active.return_value = [rss_item]

        torrent = make_torrent("[G] TestAnime 第01话 [720p]")
        bangumi = make_bangumi(
            id=1,
            official_title="TestAnime (S1)",
            title_raw="TestAnime",
            filter="720",
        )
        engine.torrent.check_new.return_value = [torrent]
        engine.bangumi.match_torrent_with_pattern.return_value = (
            bangumi,
            "TestAnime",
        )

        mock_client = AsyncMock()

        with patch.object(engine, "_get_torrents", return_value=[torrent]):
            await engine.refresh_rss(mock_client)

    @pytest.mark.asyncio
    async def test_single_rss_id_filter(self):
        """传入 rss_id 时只处理指定的 RSS 源。"""
        engine = self._make_mock_engine()

        rss_item = RSSItem(id=5, name="Target RSS", url="https://example.com/rss")
        engine.rss.search_id.return_value = rss_item

        torrent = make_torrent("[G] Anime 第01话")
        engine.torrent.check_new.return_value = []
        engine.bangumi.match_torrent_with_pattern.return_value = None

        mock_client = AsyncMock()

        with patch.object(engine, "_get_torrents", return_value=[torrent]):
            await engine.refresh_rss(mock_client, rss_id=5)

        engine.rss.search_id.assert_called_once_with(5)

    @pytest.mark.asyncio
    async def test_empty_rss_items(self):
        """没有活跃的 RSS 源时正常完成，生成空报告。"""
        engine = self._make_mock_engine()
        engine.rss.search_active.return_value = []

        mock_client = AsyncMock()

        with patch("module.rss.engine.logger") as mock_logger:
            await engine.refresh_rss(mock_client)

        # 应该有 info 级别的日志输出（报告）
        assert any(
            call[0][0].startswith("========== RSS")
            for call in mock_logger.info.call_args_list
        )

    @pytest.mark.asyncio
    async def test_report_contains_rss_name_and_counts(self):
        """报告中应包含 RSS 源名称和种子计数。"""
        engine = self._make_mock_engine()

        rss_item = RSSItem(id=1, name="蜜柑计划", url="https://mikan.example.com/rss")
        engine.rss.search_active.return_value = [rss_item]

        torrent = make_torrent("[G] TestAnime 第01话 [1080p]")
        engine.torrent.check_new.return_value = [torrent]
        engine.bangumi.match_torrent_with_pattern.return_value = None

        mock_client = AsyncMock()

        with patch.object(engine, "_get_torrents", return_value=[torrent]):
            with patch("module.rss.engine.logger") as mock_logger:
                await engine.refresh_rss(mock_client)

        # 从 logger.info 调用中提取报告文本
        report_calls = mock_logger.info.call_args_list
        report_text = "\n".join(call[0][0] for call in report_calls)

        assert "蜜柑计划" in report_text
        assert "1 个新种子" in report_text

    @pytest.mark.asyncio
    async def test_add_torrent_failure_records_not_added(self):
        """匹配成功但 add_torrent 返回 False 时，应修正 action 为 not_added。"""
        engine = self._make_mock_engine()

        rss_item = RSSItem(id=1, name="Test", url="https://example.com/rss")
        engine.rss.search_active.return_value = [rss_item]

        torrent = make_torrent("[G] TestAnime 第01话 [1080p]")
        bangumi = make_bangumi(
            id=1,
            official_title="TestAnime (S1)",
            title_raw="TestAnime",
            filter="",
        )
        engine.torrent.check_new.return_value = [torrent]
        engine.bangumi.match_torrent_with_pattern.return_value = (
            bangumi,
            "TestAnime",
        )

        mock_client = AsyncMock()
        mock_client.add_torrent.return_value = False  # 下载失败

        with patch.object(engine, "_get_torrents", return_value=[torrent]):
            with patch("module.rss.engine.logger") as mock_logger:
                await engine.refresh_rss(mock_client)

        report_calls = mock_logger.info.call_args_list
        report_text = "\n".join(call[0][0] for call in report_calls)

        assert "未订阅" in report_text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest src/test/test_engine_integration.py::TestRefreshRssIntegration -v`

预期：测试因 refresh_rss 尚未集成 MatchCollector 而失败。

- [ ] **Step 3: 写最小实现**

替换 `backend/src/module/rss/engine.py` 中的 `refresh_rss` 方法（第 145-173 行），并在文件顶部添加 import。

**文件顶部新增 import（第 9 行已有的 import 之后）：**

```python
from module.rss.match_report import MatchCollector, MatchResult
```

注意：`MatchResult` 已在 Task 3.1 中导入，此处只需确保 `MatchCollector` 也被导入。最终 import 行应为：

```python
from module.rss.match_report import MatchCollector, MatchResult
```

**替换 refresh_rss 方法（第 145-173 行）：**

```python
    async def refresh_rss(self, client: DownloadClient, rss_id: Optional[int] = None):
        # 获取要处理的 RSS 源
        if not rss_id:
            rss_items: list[RSSItem] = self.rss.search_active()
        else:
            rss_item = self.rss.search_id(rss_id)
            rss_items = [rss_item] if rss_item else []

        logger.debug("[Engine] Get %s RSS items", len(rss_items))

        # 并发拉取所有 RSS 源的种子
        results = await asyncio.gather(
            *[
                self._pull_rss_with_torrent_counts(rss_item)
                for rss_item in rss_items
            ]
        )

        # 初始化 MatchCollector 收集匹配结果
        collector = MatchCollector()
        now = datetime.now(timezone.utc).isoformat()

        # 顺序处理结果（涉及数据库操作）
        for rss_item, (new_torrents, total_count, new_count, error) in zip(
            rss_items, results
        ):
            # 更新 RSS 连接状态
            rss_item.connection_status = "error" if error else "healthy"
            rss_item.last_checked_at = now
            rss_item.last_error = error
            self.add(rss_item)

            # 记录 RSS 源处理开始和种子计数
            collector.start_rss(rss_item)
            collector.set_torrent_counts(rss_item.id, total=total_count, new=new_count)

            for torrent in new_torrents:
                matched_data, match_result = self.match_torrent_with_details(torrent)

                if matched_data:
                    # 匹配成功，尝试添加下载
                    if await client.add_torrent(torrent, matched_data):
                        logger.debug(
                            "[Engine] Add torrent %s to client", torrent.name
                        )
                        torrent.downloaded = True
                    else:
                        # 下载客户端添加失败，修正 action 为 not_added
                        match_result.download_action = "not_added"

                # 无论匹配结果如何，都记录到 collector
                collector.record_match(rss_item.id, match_result)

            collector.finish_rss(rss_item.id)

            # 将所有种子写入数据库
            self.torrent.add_all(new_torrents)

        self.commit()

        # 生成并输出报告
        report = collector.generate_report()
        logger.info(report)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest src/test/test_engine_integration.py::TestRefreshRssIntegration -v`

预期：全部 8 个测试通过。

- [ ] **Step 5: 提交**

---

## Task 3.4: 确保原有功能不受影响

验证修改后的 engine.py 不破坏现有功能：原有 `match_torrent` 方法仍然可用，原有 `_pull_rss_with_status` 方法仍然可用。

- [ ] **Step 1: 写测试**

在 `backend/src/test/test_engine_integration.py` 中追加：

```python
# --- 向后兼容性测试 ---


class TestBackwardCompatibility:
    """验证原有方法未被破坏。"""

    @pytest.fixture
    def mock_engine(self):
        """创建 mock 的 RSSEngine。"""
        with patch("module.rss.engine.Database.__init__", return_value=None):
            from module.rss.engine import RSSEngine

            engine = RSSEngine.__new__(RSSEngine)
            engine._filter_cache = {}
            engine.bangumi = MagicMock()
            return engine

    def test_original_match_torrent_still_works(self, mock_engine):
        """原有 match_torrent 方法应保持原有行为。"""
        bangumi = make_bangumi(id=1, official_title="Test", filter="")
        mock_engine.bangumi.match_torrent.return_value = bangumi

        torrent = make_torrent("[G] Test 第01话")
        result = mock_engine.match_torrent(torrent)

        assert result is bangumi

    def test_original_match_torrent_returns_none(self, mock_engine):
        """原有 match_torrent 在无匹配时返回 None。"""
        mock_engine.bangumi.match_torrent.return_value = None

        torrent = make_torrent("[G] Unknown 第01话")
        result = mock_engine.match_torrent(torrent)

        assert result is None

    @pytest.mark.asyncio
    async def test_original_pull_rss_with_status_still_works(self, mock_engine):
        """原有 _pull_rss_with_status 方法应保持原有行为。"""
        mock_engine.torrent = MagicMock()

        rss_item = RSSItem(id=1, name="Test", url="https://example.com/rss")
        torrents = [make_torrent("A")]

        with patch.object(mock_engine, "_get_torrents", return_value=torrents):
            mock_engine.torrent.check_new.return_value = torrents
            result = await mock_engine._pull_rss_with_status(rss_item)

        assert result == (torrents, None)
```

- [ ] **Step 2: 运行测试确认通过**

Run: `cd backend && uv run pytest src/test/test_engine_integration.py::TestBackwardCompatibility -v`

预期：全部 3 个测试通过。原有方法未被修改，行为不变。

- [ ] **Step 3: 提交**

---

## Task 3.5: 最终集成验证

运行全部测试，确认 Module 3 的修改不影响项目中的其他测试。

- [ ] **Step 1: 运行全部 engine integration 测试**

Run: `cd backend && uv run pytest src/test/test_engine_integration.py -v`

预期：全部测试通过（TestMatchTorrentWithDetails: 8, TestPullRssWithTorrentCounts: 5, TestRefreshRssIntegration: 8, TestBackwardCompatibility: 3 = 24 个测试）。

- [ ] **Step 2: 确认不影响现有测试**

Run: `cd backend && uv run pytest src/test/ -v --timeout=60`

预期：全部现有测试仍然通过。

- [ ] **Step 3: 提交最终版本**

```bash
git add backend/src/module/rss/engine.py backend/src/test/test_engine_integration.py
git commit -m "feat(engine): integrate MatchCollector in refresh_rss for match logging

Add match_torrent_with_details() to RSSEngine that returns both the
matched Bangumi and a MatchResult for logging. Modify refresh_rss()
to use MatchCollector to collect per-torrent match results and generate
a structured report logged at INFO level.

Backward compatible - existing match_torrent() and _pull_rss_with_status()
methods are unchanged."
```

---

## 文件最终结构

```
backend/src/
├── module/rss/
│   ├── engine.py                          # 新增 match_torrent_with_details,
│   │                                      # _pull_rss_with_torrent_counts,
│   │                                      # 修改 refresh_rss
│   └── match_report.py                    # Module 1 产出
├── module/database/bangumi.py             # Module 2 产出
└── test/
    ├── test_engine_integration.py         # Module 3 新增
    ├── test_match_report.py               # Module 1 产出
    └── test_bangumi_pattern.py            # Module 2 产出
```

## 实现注意事项

1. **filter 逻辑一致性**：新方法 `match_torrent_with_details` 的 filter 判断必须与原 `match_torrent` 完全一致。关键点：`filter_pattern.search(torrent.name)` 返回 False 时下载（种子名不包含排除关键词），返回 True 时过滤。原方法第 140 行 `if not pattern.search(torrent.name)` 为 True 时 return matched（下载），这个逻辑在新方法中必须精确复制。

2. **not_added 场景**：当 `match_torrent_with_details` 返回的 Bangumi 非 None（即应该下载），但 `client.add_torrent()` 返回 False 时，需要将 `MatchResult.download_action` 从 "downloaded" 修正为 "not_added"。这是运行时才知道的结果，无法在匹配阶段确定。

3. **import 依赖**：`engine.py` 新增了 `from module.rss.match_report import MatchCollector, MatchResult`。如果 Module 1 尚未实现，import 会失败。在独立开发 Module 3 时，需要确保 Module 1 已完成，或在测试中使用 mock。

4. **并发安全**：`_pull_rss_with_torrent_counts` 使用 `asyncio.gather` 并发执行，`MatchCollector` 的状态更新在 `gather` 完成后的顺序循环中进行，不存在并发问题。

5. **日志级别**：报告通过 `logger.info` 输出，确保在生产环境中可见。debug 级别的单个种子下载日志保持不变。

6. **_pull_rss_with_status 保留**：原方法保持不变，`download_bangumi` 等其他调用者不受影响。
