import pytest
from module.manager.renamer import Renamer, RenameInfo


class TestRenameInfo:
    def test_rename_info_fields(self):
        info = RenameInfo(1, 2, "test_title")
        assert info.episode_offset == 1
        assert info.season_offset == 2
        assert info.dandanplay_title == "test_title"

    def test_rename_info_default(self):
        info = RenameInfo(0, 0, None)
        assert info.dandanplay_title is None


class TestRenamerDandanplayMethod:
    def test_gen_path_dandanplay(self):
        from module.models import EpisodeFile

        file_info = EpisodeFile(
            title="E", season=1, episode=1, suffix=".mkv", media_path="/test.mkv"
        )
        result = Renamer.gen_path(file_info, "葬送的芙莉莲", "dandanplay")
        assert result == "葬送的芙莉莲 S01E01.mkv"

    def test_gen_path_dandanplay_fallback(self):
        """dandanplay_title 为 None 时 fallback 到 advance 行为"""
        from module.models import EpisodeFile

        file_info = EpisodeFile(
            title="E", season=1, episode=1, suffix=".mkv", media_path="/test.mkv"
        )
        result = Renamer.gen_path(file_info, "Frieren", "dandanplay")
        assert result == "Frieren S01E01.mkv"

    def test_gen_path_subtitle_dandanplay(self):
        from module.models import SubtitleFile

        file_info = SubtitleFile(
            title="E", season=1, episode=1,
            suffix=".ass", language="zh", media_path="/test.ass"
        )
        result = Renamer.gen_path(file_info, "葬送的芙莉莲", "subtitle_dandanplay")
        assert result == "葬送的芙莉莲 S01E01.zh.ass"
