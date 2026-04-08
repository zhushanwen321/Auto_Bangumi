import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestDandanplayFetch:
    async def test_fetch_dandanplay_title_success(self):
        """成功获取弹弹 Play 番名应写入 dandanplay_title"""
        mock_client = AsyncMock()
        mock_client.search.return_value = "葬送的芙莉莲"

        with patch("module.searcher.dandanplay.DandanplayClient", return_value=mock_client):
            from module.searcher.dandanplay import fetch_dandanplay_title

            result = await fetch_dandanplay_title("Frieren", "app_id", "app_secret")
            assert result == "葬送的芙莉莲"

    async def test_fetch_dandanplay_title_no_result(self):
        """弹弹 Play 无结果应返回 None"""
        mock_client = AsyncMock()
        mock_client.search.return_value = None

        with patch("module.searcher.dandanplay.DandanplayClient", return_value=mock_client):
            from module.searcher.dandanplay import fetch_dandanplay_title

            result = await fetch_dandanplay_title("unknown", "app_id", "app_secret")
            assert result is None

    async def test_fetch_dandanplay_title_empty_input(self):
        """空标题或空 app_id 应返回 None"""
        from module.searcher.dandanplay import fetch_dandanplay_title

        assert await fetch_dandanplay_title("", "app_id", "secret") is None
        assert await fetch_dandanplay_title("title", "", "secret") is None
