import pytest
from module.models.bangumi import Bangumi, BangumiUpdate
from module.models.config import Config


class TestBangumiDandanplayField:
    def test_bangumi_has_dandanplay_title(self):
        b = Bangumi(official_title="test")
        assert hasattr(b, "dandanplay_title")
        assert b.dandanplay_title is None

    def test_bangumi_has_dandanplay_retry_count(self):
        b = Bangumi(official_title="test")
        assert hasattr(b, "dandanplay_retry_count")
        assert b.dandanplay_retry_count == 0

    def test_bangumi_update_has_dandanplay_title(self):
        # Test that dandanplay_title field exists in BangumiUpdate model
        assert "dandanplay_title" in BangumiUpdate.model_fields
        # Test with all required fields
        u = BangumiUpdate(
            official_title="test",
            title_raw="test",
            year="2024",
            season_raw="1",
            group_name="test",
            dpi="1080p",
            source="test",
            subtitle="test",
            poster_link="test",
            rule_name="test",
            save_path="test",
        )
        assert u.dandanplay_title is None
        # Test setting dandanplay_title
        u2 = BangumiUpdate(
            official_title="test",
            title_raw="test",
            year="2024",
            season_raw="1",
            group_name="test",
            dpi="1080p",
            source="test",
            subtitle="test",
            poster_link="test",
            rule_name="test",
            save_path="test",
            dandanplay_title="some title",
        )
        assert u2.dandanplay_title == "some title"


class TestDandanplayConfig:
    def test_config_has_dandanplay(self):
        config = Config()
        assert hasattr(config, "dandanplay")
        assert config.dandanplay.enable is False
        assert config.dandanplay.app_id == ""
        assert config.dandanplay.app_secret == ""
