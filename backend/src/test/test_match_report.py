"""MatchReport 模块测试。"""

from dataclasses import fields

import pytest

from module.rss.match_report import MatchResult, RSSResult


class TestMatchResult:
    """MatchResult 数据结构测试。"""

    def test_create_with_defaults(self):
        """使用默认值创建 MatchResult。"""
        result = MatchResult(
            torrent_name="[Group] Test Anime 第01话 [1080p]",
            matched_bangumi=None,
            download_action="not_matched",
        )
        assert result.torrent_name == "[Group] Test Anime 第01话 [1080p]"
        assert result.matched_bangumi is None
        assert result.download_action == "not_matched"
        assert result.matched_pattern is None
        assert result.filter_reason is None

    def test_create_with_all_fields(self):
        """设置所有字段创建 MatchResult。"""
        result = MatchResult(
            torrent_name="[Group] Test Anime 第01话 [1080p]",
            matched_bangumi="Test Anime (S1)",
            download_action="downloaded",
            matched_pattern="Test Anime",
            filter_reason=None,
        )
        assert result.matched_bangumi == "Test Anime (S1)"
        assert result.download_action == "downloaded"
        assert result.matched_pattern == "Test Anime"

    def test_download_action_values(self):
        """download_action 应该接受预定义的四种值。"""
        valid_actions = {"downloaded", "filtered", "not_matched", "not_added"}
        for action in valid_actions:
            result = MatchResult(
                torrent_name="test",
                matched_bangumi=None,
                download_action=action,
            )
            assert result.download_action == action

    def test_has_expected_fields(self):
        """验证 MatchResult 包含所有预期字段。"""
        field_names = {f.name for f in fields(MatchResult)}
        assert field_names == {
            "torrent_name",
            "matched_bangumi",
            "download_action",
            "matched_pattern",
            "filter_reason",
        }


class TestRSSResult:
    """RSSResult 数据结构测试。"""

    def test_create_with_defaults(self):
        """使用默认值创建 RSSResult。"""
        result = RSSResult(
            rss_name="Mikan Project",
            rss_id=1,
        )
        assert result.rss_name == "Mikan Project"
        assert result.rss_id == 1
        assert result.total_torrents == 0
        assert result.new_torrents == 0
        assert result.matches == []

    def test_create_with_counts(self):
        """设置种子计数。"""
        result = RSSResult(
            rss_name="DMHY",
            rss_id=2,
            total_torrents=100,
            new_torrents=15,
        )
        assert result.total_torrents == 100
        assert result.new_torrents == 15

    def test_matches_list_can_hold_match_results(self):
        """matches 列表可以存放 MatchResult 对象。"""
        match = MatchResult(
            torrent_name="[Group] Test 第01话",
            matched_bangumi="Test (S1)",
            download_action="downloaded",
            matched_pattern="Test",
        )
        result = RSSResult(rss_name="Test RSS", rss_id=1, matches=[match])
        assert len(result.matches) == 1
        assert result.matches[0].torrent_name == "[Group] Test 第01话"

    def test_has_expected_fields(self):
        """验证 RSSResult 包含所有预期字段。"""
        field_names = {f.name for f in fields(RSSResult)}
        assert field_names == {
            "rss_name",
            "rss_id",
            "total_torrents",
            "new_torrents",
            "matches",
        }
