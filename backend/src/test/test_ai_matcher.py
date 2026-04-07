import pytest
from unittest.mock import MagicMock, patch
from module.searcher.ai_matcher import AIMatcher, MatchResult


def _make_mock_response(content: str) -> MagicMock:
    """Create a mock OpenAI response with the given JSON content string."""
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = content
    return mock_resp


class TestAIMatcherGenerateKeywords:
    async def test_generate_keywords_returns_list(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_response(
            '{"keywords": ["葬送的芙莉莲", "Frieren", "Sousou no Frieren"]}'
        )
        with patch("module.searcher.ai_matcher.OpenAI", return_value=mock_client):
            matcher = AIMatcher(openai_config={"api_key": "test"})
            keywords = await matcher._generate_keywords("葬送的芙莉莲 S01E01")
        assert keywords == ["葬送的芙莉莲", "Frieren", "Sousou no Frieren"]

    async def test_generate_keywords_empty_result(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_response(
            '{"keywords": []}'
        )
        with patch("module.searcher.ai_matcher.OpenAI", return_value=mock_client):
            matcher = AIMatcher(openai_config={"api_key": "test"})
            keywords = await matcher._generate_keywords("test")
        assert keywords == []


class TestAIMatcherDeduplicate:
    def test_deduplicate_by_id(self):
        results = [
            {"id": 1, "name": "A"},
            {"id": 2, "name": "B"},
            {"id": 1, "name": "A (duplicate)"},
        ]
        matcher = AIMatcher.__new__(AIMatcher)
        deduped = matcher._deduplicate(results, key_fn=lambda x: x["id"])
        assert len(deduped) == 2
        assert deduped[0]["id"] == 1


class TestAIMatcherSearchAndMatch:
    async def test_search_and_match_success(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_mock_response('{"keywords": ["keyword1"]}'),
            _make_mock_response('{"index": 0, "confidence": 0.9}'),
        ]

        async def mock_search(keyword):
            return [{"id": 1, "name": "Test Anime"}]

        def mock_formatter(results):
            return "1. Test Anime"

        with patch("module.searcher.ai_matcher.OpenAI", return_value=mock_client):
            matcher = AIMatcher(openai_config={"api_key": "test"})
            result = await matcher.search_and_match(
                title="Test",
                search_fn=mock_search,
                result_formatter=mock_formatter,
            )

        assert result is not None
        assert result.confidence == 0.9
        assert result.matched_item["name"] == "Test Anime"

    async def test_search_and_match_no_results(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_response(
            '{"keywords": ["keyword1"]}'
        )

        async def mock_search(keyword):
            return []

        with patch("module.searcher.ai_matcher.OpenAI", return_value=mock_client):
            matcher = AIMatcher(openai_config={"api_key": "test"})
            result = await matcher.search_and_match(
                title="Test",
                search_fn=mock_search,
                result_formatter=lambda r: "",
            )

        assert result is None

    async def test_search_and_match_low_confidence(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_mock_response('{"keywords": ["keyword1"]}'),
            _make_mock_response('{"index": 0, "confidence": 0.3}'),
        ]

        async def mock_search(keyword):
            return [{"id": 1, "name": "Test"}]

        with patch("module.searcher.ai_matcher.OpenAI", return_value=mock_client):
            matcher = AIMatcher(openai_config={"api_key": "test"})
            result = await matcher.search_and_match(
                title="Test",
                search_fn=mock_search,
                result_formatter=lambda r: "1. Test",
            )

        assert result is None
