import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from module.models.bangumi import Bangumi


class TestAIEnhancedSearchTrigger:
    """Test that AI enhanced search is triggered under the right conditions."""

    @pytest.mark.asyncio
    async def test_tmdb_failed_triggers_ai(self):
        """When TMDB returns year=None and poster_link=None, AI should be triggered."""
        from module.rss.analyser import RSSAnalyser
        from module.models.rss import RSSItem
        from module.models.torrent import Torrent

        analyser = RSSAnalyser()
        bangumi = Bangumi(official_title="raw_title", title_raw="raw_title", season=1)
        rss = RSSItem(parser="tmdb", url="http://test")
        torrent = Torrent(name="test", url="http://test", homepage="")

        with patch.object(analyser, "tmdb_parser", return_value=("raw_title", 1, None, None)):
            with patch("module.rss.analyser.settings") as mock_settings:
                mock_settings.experimental_openai.enable = True
                mock_settings.rss_parser.language = "zh"
                mock_settings.experimental_openai.dict.return_value = {"api_key": "test"}

                mock_matcher_instance = MagicMock()
                mock_matcher_instance.search_and_match = AsyncMock(return_value=None)

                with patch("module.searcher.ai_matcher.AIMatcher", return_value=mock_matcher_instance):
                    await analyser.official_title_parser(bangumi, rss, torrent)
                    mock_matcher_instance.search_and_match.assert_called_once()

    @pytest.mark.asyncio
    async def test_tmdb_succeeded_skips_ai(self):
        """When TMDB returns valid results, AI should NOT be triggered."""
        from module.rss.analyser import RSSAnalyser
        from module.models.rss import RSSItem
        from module.models.torrent import Torrent

        analyser = RSSAnalyser()
        bangumi = Bangumi(official_title="raw_title", title_raw="raw_title", season=1)
        rss = RSSItem(parser="tmdb", url="http://test")
        torrent = Torrent(name="test", url="http://test", homepage="")

        with patch.object(
            analyser,
            "tmdb_parser",
            return_value=("Official Title", 1, 2024, "http://poster.jpg"),
        ):
            with patch("module.rss.analyser.settings") as mock_settings:
                mock_settings.experimental_openai.enable = True
                mock_settings.rss_parser.language = "zh"

                with patch("module.searcher.ai_matcher.AIMatcher") as MockMatcher:
                    await analyser.official_title_parser(bangumi, rss, torrent)
                    MockMatcher.assert_not_called()

    @pytest.mark.asyncio
    async def test_ai_disabled_skips_ai(self):
        """When AI is disabled, AI search should NOT be triggered even if TMDB fails."""
        from module.rss.analyser import RSSAnalyser
        from module.models.rss import RSSItem
        from module.models.torrent import Torrent

        analyser = RSSAnalyser()
        bangumi = Bangumi(official_title="raw_title", title_raw="raw_title", season=1)
        rss = RSSItem(parser="tmdb", url="http://test")
        torrent = Torrent(name="test", url="http://test", homepage="")

        with patch.object(analyser, "tmdb_parser", return_value=("raw_title", 1, None, None)):
            with patch("module.rss.analyser.settings") as mock_settings:
                mock_settings.experimental_openai.enable = False
                mock_settings.rss_parser.language = "zh"

                with patch("module.searcher.ai_matcher.AIMatcher") as MockMatcher:
                    await analyser.official_title_parser(bangumi, rss, torrent)
                    MockMatcher.assert_not_called()

    @pytest.mark.asyncio
    async def test_mikan_failed_triggers_ai(self):
        """When Mikan raises AttributeError, AI should be triggered."""
        from module.rss.analyser import RSSAnalyser
        from module.models.rss import RSSItem
        from module.models.torrent import Torrent

        analyser = RSSAnalyser()
        bangumi = Bangumi(official_title="raw_title", title_raw="raw_title", season=1)
        rss = RSSItem(parser="mikan", url="http://test")
        torrent = Torrent(name="test", url="http://test", homepage=None)

        with patch.object(analyser, "mikan_parser", side_effect=AttributeError("no homepage")):
            with patch("module.rss.analyser.settings") as mock_settings:
                mock_settings.experimental_openai.enable = True
                mock_settings.rss_parser.language = "zh"
                mock_settings.experimental_openai.dict.return_value = {"api_key": "test"}

                mock_matcher_instance = MagicMock()
                mock_matcher_instance.search_and_match = AsyncMock(return_value=None)

                with patch("module.searcher.ai_matcher.AIMatcher", return_value=mock_matcher_instance):
                    await analyser.official_title_parser(bangumi, rss, torrent)
                    mock_matcher_instance.search_and_match.assert_called_once()
