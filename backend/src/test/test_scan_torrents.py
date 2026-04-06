"""Scan Torrents 功能测试。"""

import pytest
from module.models.torrent import (
    ScannedTorrent,
    ScanTorrentsResponse,
    RecollectByUrlsRequest,
)


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
