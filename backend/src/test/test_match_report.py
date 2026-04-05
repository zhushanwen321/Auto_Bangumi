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
            "pattern_type",
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


class TestGenerateReportMatches:
    """匹配详情报告测试。"""

    def _build_collector_with_all_actions(self) -> MatchCollector:
        """构造一个包含四种 action 的完整 collector。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Mikan Project"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, total=50, new=12)

        # downloaded
        collector.record_match(1, MatchResult(
            torrent_name="[Group] 推しの子 第13话 [1080p HEVC]",
            matched_bangumi="推しの子 (S1)",
            download_action="downloaded",
            matched_pattern="推しの子",
            pattern_type="title_raw",
        ))

        # filtered
        collector.record_match(1, MatchResult(
            torrent_name="[Group] 推し之子 第13话 [720p]",
            matched_bangumi="推しの子 (S1)",
            download_action="filtered",
            matched_pattern="推し之子",
            pattern_type="alias",
            filter_reason="种子名称不匹配 filter 正则 /1080p/",
        ))

        # not_matched
        collector.record_match(1, MatchResult(
            torrent_name="[Group] 未知的动漫 第01话",
            matched_bangumi=None,
            download_action="not_matched",
        ))

        # not_added
        collector.record_match(1, MatchResult(
            torrent_name="[Group] 新番测试 第01话",
            matched_bangumi="新番测试 (S1)",
            download_action="not_added",
            matched_pattern="新番测试",
        ))

        collector.finish_rss(1)
        return collector

    def test_downloaded_section(self):
        """报告应包含 [下载] 分类，显示成功下载的种子。"""
        collector = self._build_collector_with_all_actions()
        report = collector.generate_report()

        assert "[下载] 成功下载 (1 个):" in report
        assert "推しの子 (S1):" in report
        assert "[Group] 推しの子 第13话 [1080p HEVC]" in report
        assert '匹配: title_raw="推しの子"' in report

    def test_filtered_section(self):
        """报告应包含 [过滤] 分类，显示被过滤的种子及原因。"""
        collector = self._build_collector_with_all_actions()
        report = collector.generate_report()

        assert "[过滤] 匹配但被过滤 (1 个):" in report
        assert "推しの子 (S1):" in report
        assert "[Group] 推し之子 第13话 [720p]" in report
        assert '匹配: alias="推し之子"' in report
        assert "种子名称不匹配 filter 正则 /1080p/" in report

    def test_not_matched_section(self):
        """报告应包含 [未匹配] 分类，显示未匹配任何番剧的种子。"""
        collector = self._build_collector_with_all_actions()
        report = collector.generate_report()

        assert "[未匹配] 未匹配任何 Bangumi (1 个):" in report
        assert "[Group] 未知的动漫 第01话" in report

    def test_not_added_section(self):
        """报告应包含 [未订阅] 分类，显示匹配但未添加下载的种子。"""
        collector = self._build_collector_with_all_actions()
        report = collector.generate_report()

        assert "[未订阅] 已匹配但未添加下载 (1 个):" in report
        assert "新番测试 (S1):" in report
        assert "[Group] 新番测试 第01话" in report

    def test_empty_category_not_shown(self):
        """某个分类为空时不应出现在报告中。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Test"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, total=5, new=1)
        # 只有 downloaded，没有其他分类
        collector.record_match(1, MatchResult(
            torrent_name="[G] A 第01话",
            matched_bangumi="A (S1)",
            download_action="downloaded",
            matched_pattern="A",
        ))
        collector.finish_rss(1)

        report = collector.generate_report()

        assert "[下载] 成功下载 (1 个):" in report
        assert "[过滤]" not in report
        assert "[未匹配]" not in report
        assert "[未订阅]" not in report

    def test_multiple_downloads_grouped_by_bangumi(self):
        """同一番剧的多个下载种子应归组显示。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Test"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, total=10, new=2)

        collector.record_match(1, MatchResult(
            torrent_name="[G] 芙莉莲 第12话 [1080p]",
            matched_bangumi="葬送的芙莉莲 (S1)",
            download_action="downloaded",
            matched_pattern="芙莉莲",
        ))
        collector.record_match(1, MatchResult(
            torrent_name="[G] 芙莉莲 第11话 [1080p]",
            matched_bangumi="葬送的芙莉莲 (S1)",
            download_action="downloaded",
            matched_pattern="芙莉莲",
        ))

        collector.finish_rss(1)
        report = collector.generate_report()

        # "葬送的芙莉莲 (S1)" 只出现一次作为分组标题
        # 两话都应出现
        assert report.count("葬送的芙莉莲 (S1):") == 1
        assert "[G] 芙莉莲 第12话 [1080p]" in report
        assert "[G] 芙莉莲 第11话 [1080p]" in report


class TestGenerateReportFullScenario:
    """完整的报告生成端到端测试。"""

    def test_full_report_format(self):
        """完整报告应匹配预期格式。"""
        collector = MatchCollector()

        class FakeMikan:
            id = 1
            name = "Mikan Project"

        class FakeDMHY:
            id = 2
            name = "DMHY"

        # RSS 1: Mikan
        collector.start_rss(FakeMikan())
        collector.set_torrent_counts(1, total=50, new=4)
        collector.record_match(1, MatchResult(
            torrent_name="[Group] 推しの子 第13话 [1080p HEVC]",
            matched_bangumi="推しの子 (S1)",
            download_action="downloaded",
            matched_pattern="推しの子",
        ))
        collector.record_match(1, MatchResult(
            torrent_name="[Group] 推し之子 第13话 [720p]",
            matched_bangumi="推しの子 (S1)",
            download_action="filtered",
            matched_pattern="推し之子",
            filter_reason="种子名称不匹配 filter 正则 /1080p/",
        ))
        collector.record_match(1, MatchResult(
            torrent_name="[Group] 未知的动漫 第01话",
            matched_bangumi=None,
            download_action="not_matched",
        ))
        collector.record_match(1, MatchResult(
            torrent_name="[Group] 新番测试 第01话",
            matched_bangumi="新番测试 (S1)",
            download_action="not_added",
            matched_pattern="新番测试",
        ))
        collector.finish_rss(1)

        # RSS 2: DMHY (只有 downloaded)
        collector.start_rss(FakeDMHY())
        collector.set_torrent_counts(2, total=30, new=1)
        collector.record_match(2, MatchResult(
            torrent_name="[Sub] 芙莉莲 第12话 [1080p]",
            matched_bangumi="葬送的芙莉莲 (S1)",
            download_action="downloaded",
            matched_pattern="芙莉莲",
        ))
        collector.finish_rss(2)

        report = collector.generate_report()

        # 全局结构
        assert report.startswith("========== RSS 刷新报告 ==========\n")
        assert report.rstrip().endswith("=================================")
        assert "处理了 2 个 RSS 源" in report

        # RSS 1 内容
        assert "--- 源: Mikan Project ---" in report
        assert "获取 50 个种子，其中 4 个新种子" in report

        # RSS 2 内容
        assert "--- 源: DMHY ---" in report
        assert "获取 30 个种子，其中 1 个新种子" in report

        # 汇总
        assert "汇总: 5 个新种子 -> 2 个下载, 1 个过滤, 1 个未匹配, 1 个未订阅" in report

    def test_report_without_summary_when_no_new_torrents(self):
        """没有新种子时不应该有汇总行。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Empty"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, total=10, new=0)
        collector.finish_rss(1)

        report = collector.generate_report()
        assert "汇总" not in report

    def test_collector_can_be_reused(self):
        """同一 collector 实例可以多次调用 generate_report。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Test"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, total=5, new=1)
        collector.record_match(1, MatchResult(
            torrent_name="A",
            matched_bangumi="B",
            download_action="downloaded",
            matched_pattern="B",
        ))
        collector.finish_rss(1)

        report1 = collector.generate_report()
        report2 = collector.generate_report()

        assert report1 == report2


class TestGenerateReportEdgeCases:
    """报告生成的边界情况测试。"""

    def test_special_characters_in_torrent_name(self):
        """种子名称包含特殊字符时不应破坏报告格式。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Test"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, total=1, new=1)
        collector.record_match(1, MatchResult(
            torrent_name="[Group] Test <script> 第01话 [1080p/HEVC]",
            matched_bangumi="Test (S1)",
            download_action="downloaded",
            matched_pattern="Test",
        ))
        collector.finish_rss(1)

        report = collector.generate_report()
        assert "[Group] Test <script> 第01话 [1080p/HEVC]" in report

    def test_empty_torrent_name(self):
        """空的种子名称不应导致崩溃。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Test"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, total=1, new=1)
        collector.record_match(1, MatchResult(
            torrent_name="",
            matched_bangumi=None,
            download_action="not_matched",
        ))
        collector.finish_rss(1)

        report = collector.generate_report()
        assert "[未匹配]" in report

    def test_none_pattern_in_downloaded(self):
        """downloaded 结果没有 matched_pattern 时应优雅处理。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Test"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, total=1, new=1)
        collector.record_match(1, MatchResult(
            torrent_name="[G] Test 第01话",
            matched_bangumi="Test (S1)",
            download_action="downloaded",
            matched_pattern=None,
        ))
        collector.finish_rss(1)

        report = collector.generate_report()
        assert "[下载]" in report
        # matched_pattern 为 None 时输出 "None" 字符串
        assert '匹配: pattern="None"' in report

    def test_no_filter_reason_in_filtered(self):
        """filtered 结果没有 filter_reason 时不应崩溃。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Test"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, total=1, new=1)
        collector.record_match(1, MatchResult(
            torrent_name="[G] Test 第01话",
            matched_bangumi="Test (S1)",
            download_action="filtered",
            matched_pattern="Test",
            filter_reason=None,
        ))
        collector.finish_rss(1)

        report = collector.generate_report()
        assert "[过滤]" in report

    def test_unicode_rss_name(self):
        """RSS 源名包含中文/日文应正确显示。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "蜜柑计划 (Mikan Project)"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, total=1, new=0)
        collector.finish_rss(1)

        report = collector.generate_report()
        assert "蜜柑计划 (Mikan Project)" in report

    def test_large_volume_matches(self):
        """大量匹配结果不应导致格式错误。"""
        collector = MatchCollector()

        class FakeRSS:
            id = 1
            name = "Test"

        collector.start_rss(FakeRSS())
        collector.set_torrent_counts(1, total=1000, new=100)

        for i in range(100):
            collector.record_match(1, MatchResult(
                torrent_name=f"[G] Anime 第{i:03d}话",
                matched_bangumi="Anime (S1)",
                download_action="downloaded",
                matched_pattern="Anime",
            ))

        collector.finish_rss(1)
        report = collector.generate_report()

        assert "成功下载 (100 个):" in report
        assert "汇总: 100 个新种子 -> 100 个下载, 0 个过滤, 0 个未匹配, 0 个未订阅" in report
