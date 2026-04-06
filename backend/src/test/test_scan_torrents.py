"""Scan Torrents 功能测试。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from module.models.torrent import (
    ScannedTorrent,
    ScanTorrentsResponse,
    RecollectByUrlsRequest,
)
from module.models import Torrent

from test.factories import make_bangumi


class TestScannedTorrentModel:
    def test_full_fields(self):
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
        t = ScannedTorrent(
            name="[Group] Anime - 01 [720p].mkv",
            url="https://example.com/anime-01.torrent",
            download_action="filtered",
        )
        assert t.matched_pattern is None
        assert t.pattern_type is None
        assert t.filter_reason is None

    def test_filtered_with_reason(self):
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
    def test_empty_response(self):
        resp = ScanTorrentsResponse(
            report="RSS 中无匹配当前番剧的种子",
            torrents=[],
        )
        assert len(resp.torrents) == 0
        assert "无匹配" in resp.report

    def test_with_torrents(self):
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
    def test_normal_urls(self):
        req = RecollectByUrlsRequest(
            torrent_urls=[
                "https://example.com/a.torrent",
                "https://example.com/b.torrent",
            ]
        )
        assert len(req.torrent_urls) == 2

    def test_empty_urls(self):
        req = RecollectByUrlsRequest(torrent_urls=[])
        assert len(req.torrent_urls) == 0


# ---------------------------------------------------------------------------
# Task 2: scan_bangumi_torrents 测试
# ---------------------------------------------------------------------------


class TestScanBangumiTorrents:
    """RSSEngine.scan_bangumi_torrents() 方法测试。"""

    def _make_mock_engine(self):
        with patch("module.rss.engine.Database.__init__", return_value=None):
            from module.rss.engine import RSSEngine

            engine = RSSEngine.__new__(RSSEngine)
            engine._filter_cache = {}
            engine.bangumi = MagicMock()
            return engine

    @pytest.mark.asyncio
    async def test_normal_match_downloaded(self):
        engine = self._make_mock_engine()
        bangumi = make_bangumi(id=10, title_raw="TestAnime", filter="")
        engine.bangumi.search_id.return_value = bangumi

        torrent = Torrent(
            name="[Group] TestAnime - 01 [1080p].mkv",
            url="https://example.com/ep01.torrent",
        )

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

        with patch("module.rss.engine.RequestContent") as MockReq:
            mock_inst = AsyncMock()
            mock_inst.get_torrents = AsyncMock(return_value=[torrent])
            MockReq.return_value.__aenter__ = AsyncMock(return_value=mock_inst)
            MockReq.return_value.__aexit__ = AsyncMock(return_value=False)
            results, report = await engine.scan_bangumi_torrents(10)

        assert len(results) == 1
        assert results[0].download_action == "downloaded"

    @pytest.mark.asyncio
    async def test_filtered_torrent_included(self):
        """filtered 分支不设置 bangumi_id，但 scan 通过 matched_bangumi 仍能捕获"""
        engine = self._make_mock_engine()
        bangumi = make_bangumi(id=10, title_raw="TestAnime", filter="720")
        engine.bangumi.search_id.return_value = bangumi

        torrent = Torrent(
            name="[Group] TestAnime - 01 [720p].mkv",
            url="https://example.com/ep01.torrent",
        )

        def mock_match(t):
            # filtered: NOT setting t.bangumi_id, but matched_bangumi points to current bangumi
            return None, MagicMock(
                torrent_name=t.name,
                matched_bangumi=bangumi.official_title,
                download_action="filtered",
                matched_pattern="TestAnime",
                pattern_type="title_raw",
                filter_reason="种子名称匹配 filter 正则 /720/",
            )

        engine.match_torrent_with_details = mock_match

        with patch("module.rss.engine.RequestContent") as MockReq:
            mock_inst = AsyncMock()
            mock_inst.get_torrents = AsyncMock(return_value=[torrent])
            MockReq.return_value.__aenter__ = AsyncMock(return_value=mock_inst)
            MockReq.return_value.__aexit__ = AsyncMock(return_value=False)
            results, report = await engine.scan_bangumi_torrents(10)

        assert len(results) == 1
        assert results[0].download_action == "filtered"
        assert "720" in results[0].filter_reason

    @pytest.mark.asyncio
    async def test_unmatched_torrent_excluded(self):
        engine = self._make_mock_engine()
        bangumi = make_bangumi(id=10, title_raw="TestAnime", filter="")
        engine.bangumi.search_id.return_value = bangumi

        other = make_bangumi(id=20, title_raw="OtherAnime")
        torrent = Torrent(name="[Group] OtherAnime - 01", url="https://example.com/other.torrent")

        def mock_match(t):
            t.bangumi_id = 20
            return other, MagicMock(
                torrent_name=t.name,
                matched_bangumi="OtherAnime",
                download_action="downloaded",
                matched_pattern="OtherAnime",
                pattern_type="title_raw",
                filter_reason=None,
            )

        engine.match_torrent_with_details = mock_match

        with patch("module.rss.engine.RequestContent") as MockReq:
            mock_inst = AsyncMock()
            mock_inst.get_torrents = AsyncMock(return_value=[torrent])
            MockReq.return_value.__aenter__ = AsyncMock(return_value=mock_inst)
            MockReq.return_value.__aexit__ = AsyncMock(return_value=False)
            results, report = await engine.scan_bangumi_torrents(10)

        assert len(results) == 0
        assert "无匹配" in report

    @pytest.mark.asyncio
    async def test_bangumi_not_found(self):
        engine = self._make_mock_engine()
        engine.bangumi.search_id.return_value = None
        results, report = await engine.scan_bangumi_torrents(999)
        assert len(results) == 0
        assert "未找到" in report

    @pytest.mark.asyncio
    async def test_empty_rss_link(self):
        engine = self._make_mock_engine()
        bangumi = make_bangumi(id=10, rss_link="")
        engine.bangumi.search_id.return_value = bangumi
        results, report = await engine.scan_bangumi_torrents(10)
        assert len(results) == 0
        assert "未配置 RSS" in report

    @pytest.mark.asyncio
    async def test_rss_fetch_error_single_url(self):
        engine = self._make_mock_engine()
        bangumi = make_bangumi(id=10, rss_link="https://example.com/rss")
        engine.bangumi.search_id.return_value = bangumi

        with patch("module.rss.engine.RequestContent") as MockReq:
            mock_inst = AsyncMock()
            mock_inst.get_torrents = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            MockReq.return_value.__aenter__ = AsyncMock(return_value=mock_inst)
            MockReq.return_value.__aexit__ = AsyncMock(return_value=False)
            results, report = await engine.scan_bangumi_torrents(10)

        assert len(results) == 0
        assert "Connection refused" in report

    @pytest.mark.asyncio
    async def test_rss_fetch_partial_failure(self):
        engine = self._make_mock_engine()
        bangumi = make_bangumi(
            id=10, rss_link="https://bad.com/rss,https://good.com/rss"
        )
        engine.bangumi.search_id.return_value = bangumi

        t1 = Torrent(name="[G] TestAnime - 01", url="https://a.com/1")

        def mock_match(t):
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

        with patch("module.rss.engine.RequestContent") as MockReq:
            mock_inst = AsyncMock()
            mock_inst.get_torrents = AsyncMock(
                side_effect=[Exception("fail"), [t1]]
            )
            MockReq.return_value.__aenter__ = AsyncMock(return_value=mock_inst)
            MockReq.return_value.__aexit__ = AsyncMock(return_value=False)
            results, report = await engine.scan_bangumi_torrents(10)

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_multiple_rss_links(self):
        engine = self._make_mock_engine()
        bangumi = make_bangumi(
            id=10, rss_link="https://rss1.com/feed,https://rss2.com/feed"
        )
        engine.bangumi.search_id.return_value = bangumi

        t1 = Torrent(name="[G] TestAnime - 01", url="https://a.com/1")
        t2 = Torrent(name="[G] TestAnime - 02", url="https://b.com/2")

        def mock_match(t):
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

        with patch("module.rss.engine.RequestContent") as MockReq:
            mock_inst = AsyncMock()
            mock_inst.get_torrents = AsyncMock(side_effect=[[t1], [t2]])
            MockReq.return_value.__aenter__ = AsyncMock(return_value=mock_inst)
            MockReq.return_value.__aexit__ = AsyncMock(return_value=False)
            results, report = await engine.scan_bangumi_torrents(10)

        assert len(results) == 2
        assert mock_inst.get_torrents.call_count == 2

    @pytest.mark.asyncio
    async def test_report_text_format(self):
        engine = self._make_mock_engine()
        bangumi = make_bangumi(id=10, title_raw="TestAnime", filter="")
        engine.bangumi.search_id.return_value = bangumi

        t1 = Torrent(
            name="[G] TestAnime - 01 [1080p]", url="https://a.com/1"
        )
        t2 = Torrent(
            name="[G] TestAnime - 02 [720p]", url="https://a.com/2"
        )

        def mock_match(t):
            if "720p" in t.name:
                return None, MagicMock(
                    torrent_name=t.name,
                    matched_bangumi=bangumi.official_title,
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

        with patch("module.rss.engine.RequestContent") as MockReq:
            mock_inst = AsyncMock()
            mock_inst.get_torrents = AsyncMock(return_value=[t1, t2])
            MockReq.return_value.__aenter__ = AsyncMock(return_value=mock_inst)
            MockReq.return_value.__aexit__ = AsyncMock(return_value=False)
            results, report = await engine.scan_bangumi_torrents(10)

        assert len(results) == 2
        assert "下载" in report
        assert "过滤" in report


# ---------------------------------------------------------------------------
# Task 3-4: API 端点测试
# ---------------------------------------------------------------------------

from fastapi import FastAPI
from fastapi.testclient import TestClient
from module.api import v1
from module.security.api import get_current_user


@pytest.fixture
def app():
    _app = FastAPI()
    _app.include_router(v1, prefix="/api")
    return _app


@pytest.fixture
def authed_client(app):
    async def mock_user():
        return "testuser"
    app.dependency_overrides[get_current_user] = mock_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def unauthed_client(app):
    return TestClient(app)


class TestScanTorrentsEndpoint:
    def test_scan_success(self, authed_client):
        scanned = [
            ScannedTorrent(name="[G] Anime - 01", url="https://a.com/1", download_action="downloaded"),
        ]
        with patch("module.api.bangumi.RSSEngine") as MockEngine:
            mock_inst = MagicMock()
            mock_inst.scan_bangumi_torrents = AsyncMock(return_value=(scanned, "报告"))
            mock_inst.__enter__ = MagicMock(return_value=mock_inst)
            mock_inst.__exit__ = MagicMock(return_value=False)
            MockEngine.return_value = mock_inst
            resp = authed_client.post("/api/v1/bangumi/1/scan-torrents")

        assert resp.status_code == 200
        data = resp.json()
        assert "report" in data
        assert "torrents" in data
        assert len(data["torrents"]) == 1

    def test_scan_empty(self, authed_client):
        with patch("module.api.bangumi.RSSEngine") as MockEngine:
            mock_inst = MagicMock()
            mock_inst.scan_bangumi_torrents = AsyncMock(return_value=([], "无匹配"))
            mock_inst.__enter__ = MagicMock(return_value=mock_inst)
            mock_inst.__exit__ = MagicMock(return_value=False)
            MockEngine.return_value = mock_inst
            resp = authed_client.post("/api/v1/bangumi/999/scan-torrents")

        assert resp.status_code == 200
        assert resp.json()["torrents"] == []

    @patch("module.security.api.DEV_AUTH_BYPASS", False)
    def test_scan_auth_required(self, unauthed_client):
        resp = unauthed_client.post("/api/v1/bangumi/1/scan-torrents")
        assert resp.status_code == 401


class TestRecollectByUrlsEndpoint:
    def test_recollect_success(self, authed_client):
        scanned = [
            ScannedTorrent(name="[G] A - 01", url="https://a.com/1", download_action="downloaded"),
        ]
        with patch("module.api.bangumi.RSSEngine") as MockEngine, \
             patch("module.api.bangumi.DownloadClient") as MockClient:
            mock_engine = MagicMock()
            mock_engine.scan_bangumi_torrents = AsyncMock(return_value=(scanned, "报告"))
            mock_engine.bangumi = MagicMock()
            mock_engine.bangumi.search_id.return_value = make_bangumi(id=1)
            mock_engine.torrent = MagicMock()
            mock_engine.__enter__ = MagicMock(return_value=mock_engine)
            mock_engine.__exit__ = MagicMock(return_value=False)
            MockEngine.return_value = mock_engine

            mock_client = AsyncMock()
            mock_client.add_torrent = AsyncMock(return_value=True)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            resp = authed_client.post(
                "/api/v1/bangumi/1/recollect-by-urls",
                json={"torrent_urls": ["https://a.com/1"]},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] is True

    def test_recollect_ignores_missing_urls(self, authed_client):
        scanned = [
            ScannedTorrent(name="[G] A - 01", url="https://a.com/1", download_action="downloaded"),
        ]
        with patch("module.api.bangumi.RSSEngine") as MockEngine, \
             patch("module.api.bangumi.DownloadClient") as MockClient:
            mock_engine = MagicMock()
            mock_engine.scan_bangumi_torrents = AsyncMock(return_value=(scanned, "报告"))
            mock_engine.bangumi = MagicMock()
            mock_engine.bangumi.search_id.return_value = make_bangumi(id=1)
            mock_engine.torrent = MagicMock()
            mock_engine.__enter__ = MagicMock(return_value=mock_engine)
            mock_engine.__exit__ = MagicMock(return_value=False)
            MockEngine.return_value = mock_engine

            mock_client = AsyncMock()
            mock_client.add_torrent = AsyncMock(return_value=True)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            resp = authed_client.post(
                "/api/v1/bangumi/1/recollect-by-urls",
                json={"torrent_urls": ["https://a.com/1", "https://missing.com/gone"]},
            )

        assert resp.status_code == 200
        # Only 1 torrent actually processed (the missing one silently ignored)
        added = mock_engine.torrent.add_all.call_args[0][0]
        assert len(added) == 1

    def test_recollect_no_matching_urls(self, authed_client):
        scanned = [
            ScannedTorrent(name="[G] A - 01", url="https://a.com/1", download_action="downloaded"),
        ]
        with patch("module.api.bangumi.RSSEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.scan_bangumi_torrents = AsyncMock(return_value=(scanned, "报告"))
            mock_engine.bangumi = MagicMock()
            mock_engine.bangumi.search_id.return_value = make_bangumi(id=1)
            mock_engine.__enter__ = MagicMock(return_value=mock_engine)
            mock_engine.__exit__ = MagicMock(return_value=False)
            MockEngine.return_value = mock_engine

            resp = authed_client.post(
                "/api/v1/bangumi/1/recollect-by-urls",
                json={"torrent_urls": ["https://totally-different.com/missing"]},
            )

        assert resp.status_code == 400

    @patch("module.security.api.DEV_AUTH_BYPASS", False)
    def test_recollect_auth_required(self, unauthed_client):
        resp = unauthed_client.post(
            "/api/v1/bangumi/1/recollect-by-urls",
            json={"torrent_urls": ["https://a.com/1"]},
        )
        assert resp.status_code == 401
