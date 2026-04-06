"""Tests for diagnosis data structures."""

from datetime import datetime, timezone

from module.diagnosis.models import (
    AnimeDiagnosis,
    DiagnosisIssue,
    DiagnosisReport,
    FixAction,
    PreviewItem,
    TorrentDiagnosis,
)
from module.diagnosis.collector import DiagnosisCollector
from module.models import Bangumi
from module.parser import TitleParser


class TestDiagnosisIssue:
    def test_diagnosis_issue_creation(self):
        issue = DiagnosisIssue(step="parse", severity="warning", message="解析失败")
        assert issue.step == "parse"
        assert issue.severity == "warning"
        assert issue.message == "解析失败"

    def test_diagnosis_issue_all_severities(self):
        error = DiagnosisIssue(step="download", severity="error", message="下载超时")
        assert error.severity == "error"


class TestTorrentDiagnosis:
    def test_torrent_diagnosis_defaults(self):
        td = TorrentDiagnosis(torrent_name="[Group] Anime - 01 [1080p].mkv")
        assert td.torrent_name == "[Group] Anime - 01 [1080p].mkv"
        assert td.parse_result is None
        assert td.match_result is None
        assert td.filter_passed is None
        assert td.filter_reason is None
        assert td.downloaded is False
        assert td.issues == []

    def test_torrent_diagnosis_with_issues(self):
        issue = DiagnosisIssue(step="filter", severity="warning", message="被过滤")
        td = TorrentDiagnosis(
            torrent_name="test.torrent",
            filter_passed=False,
            filter_reason="分辨率不匹配",
            issues=[issue],
        )
        assert len(td.issues) == 1
        assert td.filter_passed is False
        assert td.filter_reason == "分辨率不匹配"


class TestAnimeDiagnosis:
    def test_anime_diagnosis_defaults(self):
        ad = AnimeDiagnosis(anime_title="Test Anime")
        assert ad.anime_title == "Test Anime"
        assert ad.bangumi_id is None
        assert ad.status == "ok"
        assert ad.torrents == []
        assert ad.fix_actions == []

    def test_anime_diagnosis_with_torrents(self):
        td = TorrentDiagnosis(torrent_name="a.torrent", downloaded=True)
        ad = AnimeDiagnosis(anime_title="Test", torrents=[td])
        assert len(ad.torrents) == 1
        assert ad.torrents[0].downloaded is True


class TestFixAction:
    def test_fix_action_params(self):
        action = FixAction(
            action="force_download",
            torrent_name="test.torrent",
            params={"bangumi_id": 1, "save_path": "/downloads"},
        )
        assert action.action == "force_download"
        assert action.params == {"bangumi_id": 1, "save_path": "/downloads"}

    def test_fix_action_default_params(self):
        action = FixAction(action="link_bangumi", torrent_name="test.torrent")
        assert action.params == {}


class TestPreviewItem:
    def test_preview_item(self):
        item = PreviewItem(title="Test Anime", torrent_count=5, status="matched")
        assert item.title == "Test Anime"
        assert item.torrent_count == 5
        assert item.status == "matched"
        assert item.bangumi_id is None

    def test_preview_item_defaults(self):
        item = PreviewItem(title="Another Anime")
        assert item.bangumi_id is None
        assert item.torrent_count == 0
        assert item.status == "unmatched"


class TestDiagnosisReport:
    def test_diagnosis_report_default_time(self):
        report = DiagnosisReport(rss_id=1, rss_url="http://example.com/rss")
        assert report.rss_id == 1
        assert report.rss_url == "http://example.com/rss"
        assert report.scanned_at.tzinfo == timezone.utc
        assert report.anime_list == []
        assert report.errors == []

    def test_diagnosis_report_with_data(self):
        before = datetime.now(timezone.utc)
        report = DiagnosisReport(
            rss_id=2,
            rss_url="http://example.com/rss2",
            errors=["连接超时"],
        )
        after = datetime.now(timezone.utc)
        assert before <= report.scanned_at <= after
        assert report.errors == ["连接超时"]


class TestDiagnosisCollector:
    def test_record_parse(self):
        c = DiagnosisCollector()
        c.record_parse("test torrent", None)
        c.record_parse("[Sub] Title S01E01", Bangumi(title_raw="Title"))
        assert len(c._records) == 2
        assert c._records["test torrent"].parse_result is None
        assert c._records["[Sub] Title S01E01"].parse_result is not None

    def test_record_match_result(self):
        c = DiagnosisCollector()
        c.record_match_result("t1", matched=None, filter_passed=None, filter_reason=None)
        c.record_match_result("t2", matched=Bangumi(id=1), filter_passed=True, filter_reason=None)
        assert c._records["t1"].match_result is None
        assert c._records["t2"].match_result is not None
        assert c._records["t2"].filter_passed is True

    def test_record_bangumi_create(self):
        c = DiagnosisCollector()
        c.record_bangumi_create("t1", Bangumi(title_raw="Title"))
        assert c._records["t1"].bangumi_created is True
        c.record_bangumi_create("t2", None, error="Mikan 超时")
        assert c._records["t2"].bangumi_created is False
        assert c._records["t2"].bangumi_create_error == "Mikan 超时"

    def test_build_report_groups_by_title_raw(self):
        c = DiagnosisCollector()
        b1 = Bangumi(title_raw="Title A", id=1)
        b2 = Bangumi(title_raw="Title B")
        c.record_parse("[Sub] Title A S01E01", b1)
        c.record_match_result("[Sub] Title A S01E01", b1, True, None)
        c.record_parse("[Sub] Title A S01E02", b1)
        c.record_match_result("[Sub] Title A S01E02", b1, True, None)
        c.record_parse("[Sub] Title B S01E01", b2)
        c.record_match_result("[Sub] Title B S01E01", None, None, None)
        report = c.build_report(rss_id=1, rss_url="http://test")
        assert len(report.anime_list) == 2
        a = next(a for a in report.anime_list if a.anime_title == "Title A")
        assert len(a.torrents) == 2
        assert a.status == "ok"
        b = next(a for a in report.anime_list if a.anime_title == "Title B")
        assert len(b.torrents) == 1
        assert b.status == "warning"

    def test_build_report_filters_by_title(self):
        c = DiagnosisCollector()
        c.record_parse("t1", Bangumi(title_raw="Keep", id=1))
        c.record_match_result("t1", Bangumi(id=1), True, None)
        c.record_parse("t2", Bangumi(title_raw="Skip"))
        c.record_match_result("t2", None, None, None)
        report = c.build_report(1, "http://test", anime_titles=["Keep"])
        assert len(report.anime_list) == 1
        assert report.anime_list[0].anime_title == "Keep"


class TestRawParserInjection:
    def test_raw_parser_with_collector_records_result(self):
        c = DiagnosisCollector()
        result = TitleParser.raw_parser("[桜都字幕组] 葬送的芙莉莲 S01E01", collector=c)
        assert result is not None
        assert len(c._records) == 1
        rec = list(c._records.values())[0]
        assert rec.parse_result is not None
        assert rec.parse_result.title_raw is not None

    def test_raw_parser_without_collector_unchanged(self):
        result = TitleParser.raw_parser("[桜都字幕组] 葬送的芙莉莲 S01E01")
        assert result is not None

    def test_raw_parser_collects_failure(self):
        c = DiagnosisCollector()
        result = TitleParser.raw_parser("total garbage 12345 !!!", collector=c)
        # 无论 raw_parser 是否返回 None，collector 都应该记录
        rec = list(c._records.values())[0]
        assert rec.parse_result is None


class TestMatchTorrentInjection:
    def _make_engine(self):
        """创建不需要真实数据库的 RSSEngine 实例。"""
        from unittest.mock import MagicMock
        from module.rss.engine import RSSEngine

        engine = RSSEngine.__new__(RSSEngine)
        engine._filter_cache = {}
        engine.bangumi = MagicMock()
        return engine

    def test_unmatched_torrent_records_in_collector(self):
        from module.diagnosis import DiagnosisCollector
        from module.models import Torrent

        c = DiagnosisCollector()
        engine = self._make_engine()
        engine.bangumi.match_torrent.return_value = None
        t = Torrent(name="[Sub] 完全不存在的番剧 XYZ S99E99", url="magnet:?")
        result = engine.match_torrent(t, collector=c)
        assert result is None
        rec = c._records.get("[Sub] 完全不存在的番剧 XYZ S99E99")
        assert rec is not None
        assert rec.match_result is None
        assert rec.filter_passed is None

    def test_matched_no_filter_records_in_collector(self):
        from module.diagnosis import DiagnosisCollector
        from module.models import Torrent

        c = DiagnosisCollector()
        engine = self._make_engine()
        engine.bangumi.match_torrent.return_value = Bangumi(id=1, filter="")
        t = Torrent(name="[Sub] Test Anime S01E01", url="magnet:?")
        result = engine.match_torrent(t, collector=c)
        assert result is not None
        rec = c._records.get("[Sub] Test Anime S01E01")
        assert rec.match_result is not None
        assert rec.filter_passed is True

    def test_matched_filter_passed_records_in_collector(self):
        from module.diagnosis import DiagnosisCollector
        from module.models import Torrent

        c = DiagnosisCollector()
        engine = self._make_engine()
        # filter="720" 排除含 720 的种子，但此种子名不含 720，应通过
        engine.bangumi.match_torrent.return_value = Bangumi(id=2, filter="720")
        t = Torrent(name="[Sub] Test Anime S01E01 1080p", url="magnet:?")
        result = engine.match_torrent(t, collector=c)
        assert result is not None
        rec = c._records.get("[Sub] Test Anime S01E01 1080p")
        assert rec.match_result is not None
        assert rec.filter_passed is True

    def test_matched_filter_excluded_records_in_collector(self):
        from module.diagnosis import DiagnosisCollector
        from module.models import Torrent

        c = DiagnosisCollector()
        engine = self._make_engine()
        # filter="720" 排除含 720 的种子
        engine.bangumi.match_torrent.return_value = Bangumi(id=3, filter="720")
        t = Torrent(name="[Sub] Test Anime S01E01 720p", url="magnet:?")
        result = engine.match_torrent(t, collector=c)
        assert result is None
        rec = c._records.get("[Sub] Test Anime S01E01 720p")
        assert rec.match_result is not None
        assert rec.filter_passed is False
        assert rec.filter_reason == "720"

    def test_match_without_collector_unchanged(self):
        from module.models import Torrent

        engine = self._make_engine()
        engine.bangumi.match_torrent.return_value = None
        t = Torrent(name="[Sub] Test S01E01", url="magnet:?")
        result = engine.match_torrent(t)
        # 不传 collector 时行为不变
        assert result is None
