import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestDandanplayBackgroundTask:
    async def test_batch_update_calls_db_for_each_record(self):
        """批量更新应为每条记录调用数据库更新"""
        mock_records = [
            MagicMock(id=1, official_title="Test1"),
            MagicMock(id=2, official_title="Test2"),
        ]

        mock_client = AsyncMock()
        mock_client.search.side_effect = ["Title1", None]

        mock_db_bangumi = MagicMock()

        with (
            patch("module.searcher.dandanplay.DandanplayClient", return_value=mock_client),
            patch("module.database.Database") as mock_db_cls,
        ):
            mock_db_instance = MagicMock()
            mock_db_instance.bangumi = mock_db_bangumi
            mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db_instance)
            mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

            from module.searcher.dandanplay import batch_update_dandanplay_titles

            await batch_update_dandanplay_titles(
                records=mock_records,
                app_id="test",
                app_secret="test",
            )

        assert mock_db_bangumi.update_dandanplay_title.call_count == 2
