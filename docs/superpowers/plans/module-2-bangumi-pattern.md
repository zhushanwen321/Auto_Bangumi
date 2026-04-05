# Module 2: 数据库匹配增强

**目标:** 在 BangumiDatabase 中新增 `match_torrent_with_pattern()` 方法，在匹配种子名称时额外返回匹配到的具体 pattern（title_raw 或 alias），供日志记录使用。

**文件:**
- 修改: `backend/src/module/database/bangumi.py:490`（在 `match_torrent` 方法之后新增方法）
- 测试: `backend/src/test/test_bangumi_pattern.py`

---

## Task 2.1: match_torrent_with_pattern 方法实现

**文件:**
- 修改: `backend/src/module/database/bangumi.py`
- 新增: `backend/src/test/test_bangumi_pattern.py`

### 设计说明

新方法 `match_torrent_with_pattern()` 与现有 `match_torrent()` 共享相同的匹配逻辑：
- 遍历所有未删除的 Bangumi 记录
- 对每条记录检查 `title_raw` 和所有 `title_aliases`（通过 `get_all_title_patterns`）
- 选择最长匹配（更具体）
- 额外记录匹配到的 pattern 字符串

返回类型为 `Optional[tuple[Bangumi, str]]`，其中第二个元素是匹配到的 pattern。

- [ ] **Step 1: 写测试**

在 `backend/src/test/test_bangumi_pattern.py` 中：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest src/test/test_bangumi_pattern.py -v`

预期：所有测试因 `AttributeError: 'BangumiDatabase' object has no attribute 'match_torrent_with_pattern'` 而失败。

- [ ] **Step 3: 写最小实现**

在 `backend/src/module/database/bangumi.py` 中，在 `match_torrent` 方法（第 490 行 `return best_match` 之后）新增：

```python
    def match_torrent_with_pattern(
        self, torrent_name: str
    ) -> Optional[tuple[Bangumi, str]]:
        """
        匹配种子名称到 Bangumi，返回 (Bangumi, 匹配的 pattern)。

        与 match_torrent() 逻辑相同，但额外返回匹配的具体 pattern 名称，
        用于日志记录（区分 title_raw 和 alias）。

        Returns:
            (Bangumi, pattern) 如果匹配成功，pattern 是匹配的 title_raw 或 alias
            None 如果未匹配
        """
        match_datas = self.search_all()
        if not match_datas:
            return None

        best_match: Optional[Bangumi] = None
        best_pattern: Optional[str] = None
        best_match_len = 0

        for bangumi in match_datas:
            if bangumi.deleted:
                continue

            patterns = self.get_all_title_patterns(bangumi)
            for pattern in patterns:
                if pattern in torrent_name:
                    if len(pattern) > best_match_len:
                        best_match = bangumi
                        best_pattern = pattern
                        best_match_len = len(pattern)

        if best_match is not None and best_pattern is not None:
            return (best_match, best_pattern)
        return None
```

注意：此方法的匹配逻辑与 `match_torrent()` 完全一致（遍历所有未删除的 Bangumi，检查所有 pattern，选择最长匹配），唯一区别是在遍历过程中额外记录了匹配的 pattern 字符串。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest src/test/test_bangumi_pattern.py -v`

预期：所有 9 个测试通过。

- [ ] **Step 5: 提交**

```bash
git add backend/src/module/database/bangumi.py backend/src/test/test_bangumi_pattern.py
git commit -m "feat(database): add match_torrent_with_pattern method

Add BangumiDatabase.match_torrent_with_pattern() that returns both
the matched Bangumi and the specific pattern (title_raw or alias)
that matched, enabling downstream logging of which pattern was used.
Backward compatible - existing match_torrent() is unchanged."
```
