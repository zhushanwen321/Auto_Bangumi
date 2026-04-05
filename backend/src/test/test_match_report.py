"""MatchReport 模块测试。"""

from dataclasses import fields

import pytest

from module.rss.match_report import MatchCollector, MatchResult, RSSResult


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


class TestMatchCollectorLifecycle:
    """MatchCollector 生命周期方法测试。"""

    def test_start_rss_creates_entry(self):
        """start_rss 应该在 rss_results 中创建一个 RSSResult 条目。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Mikan Project"

        collector.start_rss(FakeRSS())

        assert 1 in collector.rss_results
        assert collector.rss_results[1].rss_name == "Mikan Project"
        assert collector.rss_results[1].rss_id == 1

    def test_start_rss_idempotent(self):
        """重复调用 start_rss 不会覆盖已有结果（防止意外丢失数据）。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Mikan"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, 50, 10)
        collector.start_rss(FakeRSS())  # 重复调用

        # 计数不应被重置
        assert collector.rss_results[1].total_torrents == 50
        assert collector.rss_results[1].new_torrents == 10

    def test_set_torrent_counts(self):
        """set_torrent_counts 应该正确设置种子计数。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Test"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, total=50, new=12)

        result = collector.rss_results[1]
        assert result.total_torrents == 50
        assert result.new_torrents == 12

    def test_set_torrent_counts_unknown_rss_id_raises(self):
        """对不存在的 rss_id 调用 set_torrent_counts 应该抛出 KeyError。"""
        collector = MatchCollector()

        with pytest.raises(KeyError):
            collector.set_torrent_counts(999, total=10, new=5)

    def test_record_match_downloaded(self):
        """record_match 应该记录一个下载成功的匹配结果。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Test"

        collector.start_rss(FakeRSS())

        match = MatchResult(
            torrent_name="[Group] Test 第01话",
            matched_bangumi="Test (S1)",
            download_action="downloaded",
            matched_pattern="Test",
        )
        collector.record_match(1, match)

        assert len(collector.rss_results[1].matches) == 1
        assert collector.rss_results[1].matches[0].download_action == "downloaded"

    def test_record_match_multiple(self):
        """record_match 应该能记录多个匹配结果。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Test"

        collector.start_rss(FakeRSS())

        for i in range(3):
            collector.record_match(1, MatchResult(
                torrent_name=f"Torrent {i}",
                matched_bangumi=None,
                download_action="not_matched",
            ))

        assert len(collector.rss_results[1].matches) == 3

    def test_record_match_unknown_rss_id_raises(self):
        """对不存在的 rss_id 调用 record_match 应该抛出 KeyError。"""
        collector = MatchCollector()

        with pytest.raises(KeyError):
            collector.record_match(999, MatchResult(
                torrent_name="test",
                matched_bangumi=None,
                download_action="not_matched",
            ))

    def test_finish_rss_marks_completion(self):
        """finish_rss 应该标记 RSS 处理完成（不抛异常即可）。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Test"

        collector.start_rss(FakeRSS())
        collector.finish_rss(1)  # 不应抛异常

    def test_finish_rss_unknown_id_raises(self):
        """对不存在的 rss_id 调用 finish_rss 应该抛出 KeyError。"""
        collector = MatchCollector()

        with pytest.raises(KeyError):
            collector.finish_rss(999)

    def test_multiple_rss_sources(self):
        """应该能同时跟踪多个 RSS 源。"""
        collector = MatchCollector()

        class FakeRSS1:
            id = 1
            name = "Mikan"

        class FakeRSS2:
            id = 2
            name = "DMHY"

        collector.start_rss(FakeRSS1())
        collector.start_rss(FakeRSS2())

        collector.set_torrent_counts(1, 100, 20)
        collector.set_torrent_counts(2, 80, 10)

        collector.record_match(1, MatchResult(
            torrent_name="A", matched_bangumi="B", download_action="downloaded",
        ))
        collector.record_match(2, MatchResult(
            torrent_name="C", matched_bangumi=None, download_action="not_matched",
        ))

        assert collector.rss_results[1].total_torrents == 100
        assert collector.rss_results[2].total_torrents == 80
        assert len(collector.rss_results[1].matches) == 1
        assert len(collector.rss_results[2].matches) == 1


class TestGenerateReportEmpty:
    """空报告和报告框架测试。"""

    def test_empty_report(self):
        """没有处理任何 RSS 源时，生成空报告。"""
        collector = MatchCollector()
        report = collector.generate_report()

        assert "RSS 刷新报告" in report
        assert "处理了 0 个 RSS 源" in report

    def test_report_has_header_and_footer(self):
        """报告应包含头部和尾部边界线。"""
        collector = MatchCollector()
        report = collector.generate_report()

        assert report.startswith("========== RSS 刷新报告 ==========\n")
        assert report.rstrip().endswith("=================================")

    def test_report_with_no_matches(self):
        """RSS 源没有新种子时的报告。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Empty Feed"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, total=10, new=0)
        collector.finish_rss(1)

        report = collector.generate_report()

        assert "处理了 1 个 RSS 源" in report
        assert "Empty Feed" in report
        assert "获取 10 个种子，其中 0 个新种子" in report
