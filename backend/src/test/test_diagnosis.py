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
