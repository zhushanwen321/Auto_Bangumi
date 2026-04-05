"""BangumiDatabase.match_torrent_with_pattern 方法测试。"""

import json

import pytest
from sqlmodel import Session, SQLModel, create_engine

from module.database.bangumi import BangumiDatabase
from module.models import Bangumi


@pytest.fixture
def engine():
    """创建内存 SQLite 引擎。"""
    eng = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)


@pytest.fixture
def session(engine):
    """提供测试数据库 session。"""
    with Session(engine) as sess:
        yield sess


def _make_bangumi(**overrides) -> Bangumi:
    """创建测试用 Bangumi 实例，提供合理默认值。"""
    defaults = dict(
        official_title="测试番剧",
        title_raw="TestAnime",
        season=1,
        filter="720,\\d+-\\d+",
        rss_link="",
        added=True,
        deleted=False,
    )
    defaults.update(overrides)
    return Bangumi(**defaults)


class TestMatchTorrentWithPattern:
    """match_torrent_with_pattern 方法测试。"""

    def test_match_by_title_raw(self, session):
        """通过 title_raw 匹配时，返回的 pattern 应为 title_raw 的值。"""
        bangumi = _make_bangumi(id=1, title_raw="Mushoku Tensei")
        session.add(bangumi)
        session.commit()

        db = BangumiDatabase(session)
        result = db.match_torrent_with_pattern(
            "[SubGroup] Mushoku Tensei - 01 [1080p].mkv"
        )

        assert result is not None
        matched_bangumi, pattern = result
        assert matched_bangumi.id == 1
        assert pattern == "Mushoku Tensei"

    def test_match_by_alias(self, session):
        """通过 alias 匹配时，返回的 pattern 应为匹配的 alias 值。"""
        bangumi = _make_bangumi(
            id=1,
            title_raw="Mushoku Tensei",
            title_aliases=json.dumps(["无职转生", "Jobless Reincarnation"]),
        )
        session.add(bangumi)
        session.commit()

        db = BangumiDatabase(session)
        result = db.match_torrent_with_pattern(
            "[SubGroup] 无职转生 - 01 [1080p].mkv"
        )

        assert result is not None
        matched_bangumi, pattern = result
        assert matched_bangumi.id == 1
        assert pattern == "无职转生"

    def test_prefer_longer_pattern(self, session):
        """多个 pattern 匹配时，优先选择更长的（更具体的）。"""
        bangumi = _make_bangumi(
            id=1,
            title_raw="Anime",
            title_aliases=json.dumps(["Anime Long Title"]),
        )
        session.add(bangumi)
        session.commit()

        db = BangumiDatabase(session)
        result = db.match_torrent_with_pattern(
            "[SubGroup] Anime Long Title - 01 [1080p].mkv"
        )

        assert result is not None
        _, pattern = result
        # "Anime Long Title" (16) 比 "Anime" (5) 长，应优先
        assert pattern == "Anime Long Title"

    def test_no_match_returns_none(self, session):
        """无匹配时返回 None。"""
        bangumi = _make_bangumi(id=1, title_raw="SomeOtherAnime")
        session.add(bangumi)
        session.commit()

        db = BangumiDatabase(session)
        result = db.match_torrent_with_pattern(
            "[SubGroup] Completely Different Anime - 01 [1080p].mkv"
        )

        assert result is None

    def test_empty_database_returns_none(self, session):
        """数据库为空时返回 None。"""
        db = BangumiDatabase(session)
        result = db.match_torrent_with_pattern("anything")

        assert result is None

    def test_skip_deleted_bangumi(self, session):
        """已删除的 Bangumi 不参与匹配。"""
        bangumi = _make_bangumi(
            id=1,
            title_raw="DeletedAnime",
            deleted=True,
        )
        session.add(bangumi)
        session.commit()

        db = BangumiDatabase(session)
        result = db.match_torrent_with_pattern(
            "[SubGroup] DeletedAnime - 01 [1080p].mkv"
        )

        assert result is None

    def test_cross_bangumi_selects_longest(self, session):
        """跨 Bangumi 记录时，选择最长 pattern 对应的 Bangumi。"""
        b1 = _make_bangumi(
            id=1,
            official_title="番剧A",
            title_raw="Short",
        )
        b2 = _make_bangumi(
            id=2,
            official_title="番剧B",
            title_raw="Short Title Long",
        )
        session.add(b1)
        session.add(b2)
        session.commit()

        db = BangumiDatabase(session)
        result = db.match_torrent_with_pattern(
            "[SubGroup] Short Title Long - 01 [1080p].mkv"
        )

        assert result is not None
        matched_bangumi, pattern = result
        # 两个 pattern 都能匹配，但 "Short Title Long" 更长
        assert matched_bangumi.id == 2
        assert pattern == "Short Title Long"

    def test_match_only_alias_no_title_raw(self, session):
        """title_raw 不匹配、仅 alias 匹配时，返回 alias 作为 pattern。"""
        bangumi = _make_bangumi(
            id=1,
            title_raw="OriginalTitle",
            title_aliases=json.dumps(["AliasTitle"]),
        )
        session.add(bangumi)
        session.commit()

        db = BangumiDatabase(session)
        result = db.match_torrent_with_pattern(
            "[SubGroup] AliasTitle - 01 [1080p].mkv"
        )

        assert result is not None
        matched_bangumi, pattern = result
        assert matched_bangumi.id == 1
        assert pattern == "AliasTitle"

    def test_match_with_empty_aliases(self, session):
        """title_aliases 为空时，仅通过 title_raw 匹配。"""
        bangumi = _make_bangumi(
            id=1,
            title_raw="OnlyRawTitle",
            title_aliases=None,
        )
        session.add(bangumi)
        session.commit()

        db = BangumiDatabase(session)
        result = db.match_torrent_with_pattern(
            "[SubGroup] OnlyRawTitle - 01 [1080p].mkv"
        )

        assert result is not None
        matched_bangumi, pattern = result
        assert pattern == "OnlyRawTitle"
