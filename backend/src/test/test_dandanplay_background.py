import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestDandanplayBackgroundTask:
    async def test_batch_update_calls_db_for_each_record(self):
        """批量更新应为每条记录调用数据库更新"""
        mock_db = MagicMock()
        mock_db.bangumi.get_bangumi_missing_dandanplay.return_value = [
            MagicMock(id=1, official_title="Test1", dandanplay_retry_count=0),
            MagicMock(id=2, official_title="Test2", dandanplay_retry_count=2),
        ]

        mock_client = AsyncMock()
        mock_client.search.side_effect = ["Title1", None]

        with patch("module.searcher.dandanplay.DandanplayClient", return_value=mock_client):
            from module.searcher.dandanplay import batch_update_dandanplay_titles

            await batch_update_dandanplay_titles(
                records=mock_db.bangumi.get_bangumi_missing_dandanplay.return_value,
                db=mock_db.bangumi,
                app_id="test",
                app_secret="test",
            )

        assert mock_db.bangumi.update_dandanplay_title.call_count == 2
