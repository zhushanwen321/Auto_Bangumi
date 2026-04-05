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
