import base64
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from module.searcher.dandanplay import DandanplayClient, generate_signature


class TestGenerateSignature:
    def test_signature_format(self):
        sig = generate_signature("test_id", 1234567890, "/api/v2/search/anime", "test_secret")
        decoded = base64.b64decode(sig)
        assert len(decoded) == 32

    def test_signature_deterministic(self):
        sig1 = generate_signature("id", 100, "/path", "secret")
        sig2 = generate_signature("id", 100, "/path", "secret")
        assert sig1 == sig2


class TestDandanplayClient:
    async def test_search_returns_title(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "animes": [
                {"animeTitle": "葬送的芙莉莲", "animeId": 123},
                {"animeTitle": "其他番剧", "animeId": 456},
            ]
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("module.searcher.dandanplay.httpx.AsyncClient", return_value=mock_client_instance):
            client = DandanplayClient(app_id="test", app_secret="test")
            result = await client.search("葬送的芙莉莲")

        assert result == "葬送的芙莉莲"

    async def test_search_no_results(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"animes": []}

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("module.searcher.dandanplay.httpx.AsyncClient", return_value=mock_client_instance):
            client = DandanplayClient(app_id="test", app_secret="test")
            result = await client.search("不存在的番剧")

        assert result is None
