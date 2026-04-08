from unittest.mock import patch
from module.searcher.ai_matcher import AIMatcher


class TestAIMatcherGenerateKeywords:
    async def test_generate_keywords_returns_list(self):
        with patch(
            "module.searcher.ai_matcher.call_json",
            return_value={"keywords": ["葬送的芙莉莲", "Frieren", "Sousou no Frieren"]},
        ):
            matcher = AIMatcher(openai_config={"api_key": "test"})
            keywords = await matcher._generate_keywords("葬送的芙莉莲 S01E01")
        assert keywords == ["葬送的芙莉莲", "Frieren", "Sousou no Frieren"]

    async def test_generate_keywords_empty_result(self):
        with patch(
            "module.searcher.ai_matcher.call_json",
            return_value={"keywords": []},
        ):
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
        with patch(
            "module.searcher.ai_matcher.call_json",
            side_effect=[
                {"keywords": ["keyword1"]},
                {"index": 0, "confidence": 0.9},
            ],
        ):
            matcher = AIMatcher(openai_config={"api_key": "test"})

            async def mock_search(keyword):
                return [{"id": 1, "name": "Test Anime"}]

            result = await matcher.search_and_match(
                title="Test",
                search_fn=mock_search,
                result_formatter=lambda r: "1. Test Anime",
            )

        assert result is not None
        assert result.confidence == 0.9
        assert result.matched_item["name"] == "Test Anime"

    async def test_search_and_match_no_results(self):
        with patch(
            "module.searcher.ai_matcher.call_json",
            return_value={"keywords": ["keyword1"]},
        ):
            matcher = AIMatcher(openai_config={"api_key": "test"})

            async def mock_search(keyword):
                return []

            result = await matcher.search_and_match(
                title="Test",
                search_fn=mock_search,
                result_formatter=lambda r: "",
            )

        assert result is None

    async def test_search_and_match_low_confidence(self):
        with patch(
            "module.searcher.ai_matcher.call_json",
            side_effect=[
                {"keywords": ["keyword1"]},
                {"index": 0, "confidence": 0.3},
            ],
        ):
            matcher = AIMatcher(openai_config={"api_key": "test"})

            async def mock_search(keyword):
                return [{"id": 1, "name": "Test"}]

            result = await matcher.search_and_match(
                title="Test",
                search_fn=mock_search,
                result_formatter=lambda r: "1. Test",
            )

        assert result is None
