# RSS 番剧诊断功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 RSS 管理页添加诊断功能，用户可实时扫描 RSS 查看种子匹配链路并修复问题。

**Architecture:** 注入 DiagnosisCollector 到现有解析/匹配函数，诊断和正常流程走同一代码路径。后端新增 3 个 API 端点，前端在 RSS 页面添加 Modal 组件。

**Tech Stack:** Python/FastAPI (后端), Vue 3/TypeScript (前端), SQLite

**Spec:** `docs/superpowers/specs/2026-04-06-rss-diagnosis-design.md`

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 创建 | `backend/src/module/diagnosis/__init__.py` | 包导出 |
| 创建 | `backend/src/module/diagnosis/models.py` | 数据结构 |
| 创建 | `backend/src/module/diagnosis/collector.py` | DiagnosisCollector |
| 创建 | `backend/src/module/diagnosis/service.py` | 诊断服务 |
| 创建 | `backend/src/module/api/diagnosis.py` | FastAPI 路由 |
| 创建 | `backend/src/test/test_diagnosis.py` | 后端测试 |
| 修改 | `backend/src/module/parser/title_parser.py` | raw_parser 增加 collector |
| 修改 | `backend/src/module/rss/engine.py` | match_torrent + refresh_rss 增加 collector |
| 修改 | `backend/src/module/rss/analyser.py` | torrents_to_data 增加 collector |
| 修改 | `backend/src/module/api/__init__.py` | 注册 diagnosis 路由 |
| 创建 | `webui/src/api/diagnosis.ts` | 前端 API 客户端 |
| 创建 | `webui/src/components/ab-rss-diagnosis.vue` | 诊断 Modal |
| 修改 | `webui/src/pages/index/rss.vue` | 添加诊断按钮 |
| 修改 | `webui/src/i18n/zh-CN.json` | 中文翻译 |
| 修改 | `webui/src/i18n/en.json` | 英文翻译 |

---

### Task 1: 数据结构定义

**Files:**
- 创建: `backend/src/module/diagnosis/__init__.py`
- 创建: `backend/src/module/diagnosis/models.py`
- 创建: `backend/src/test/test_diagnosis.py`

- [ ] **Step 1: 写数据结构测试**

```python
# backend/src/test/test_diagnosis.py
from module.diagnosis.models import (
    DiagnosisIssue, TorrentDiagnosis, AnimeDiagnosis,
    DiagnosisReport, FixAction, PreviewItem,
)

def test_diagnosis_issue_creation():
    issue = DiagnosisIssue(step="parse", severity="error", message="无法解析")
    assert issue.step == "parse"
    assert issue.severity == "error"

def test_torrent_diagnosis_defaults():
    td = TorrentDiagnosis(torrent_name="[SubGroup] Test S01E01")
    assert td.parse_result is None
    assert td.match_result is None
    assert td.filter_passed is None
    assert td.filter_reason is None
    assert td.downloaded is False
    assert td.issues == []

def test_anime_diagnosis():
    ad = AnimeDiagnosis(anime_title="Test", bangumi_id=1, status="ok")
    assert ad.torrents == []
    assert ad.fix_actions == []

def test_fix_action_params():
    fa = FixAction(action="force_download", torrent_name="test", params={"torrent_url": "magnet:..."})
    assert fa.action == "force_download"
    assert "torrent_url" in fa.params

def test_preview_item():
    pi = PreviewItem(title="Test", bangumi_id=1, torrent_count=5, status="matched")
    assert pi.status == "matched"

def test_diagnosis_report_default_time():
    from datetime import timezone
    r = DiagnosisReport(rss_id=1, rss_url="http://test")
    assert r.scanned_at.tzinfo == timezone.utc
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && uv run pytest src/test/test_diagnosis.py -v
```

- [ ] **Step 3: 创建包和数据结构**

```python
# backend/src/module/diagnosis/__init__.py
from .collector import DiagnosisCollector
from .models import (
    DiagnosisIssue, TorrentDiagnosis, AnimeDiagnosis,
    DiagnosisReport, FixAction, PreviewItem,
)
```

```python
# backend/src/module/diagnosis/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from module.models import Bangumi


@dataclass
class DiagnosisIssue:
    step: str       # "parse" | "bangumi_create" | "match" | "filter" | "download"
    severity: str   # "warning" | "error"
    message: str


@dataclass
class TorrentDiagnosis:
    torrent_name: str
    parse_result: Optional[Bangumi] = None
    match_result: Optional[Bangumi] = None
    # filter 是排除过滤器: True=种子没被排除, None=不涉及过滤
    filter_passed: Optional[bool] = None
    filter_reason: Optional[str] = None
    downloaded: bool = False
    issues: list[DiagnosisIssue] = field(default_factory=list)


@dataclass
class FixAction:
    action: str     # "force_download" | "link_bangumi" | "fix_parse" | "edit_filter"
    torrent_name: str
    params: dict = field(default_factory=dict)


@dataclass
class AnimeDiagnosis:
    anime_title: str
    bangumi_id: Optional[int] = None
    status: str = "ok"  # "ok" | "warning" | "error"
    torrents: list[TorrentDiagnosis] = field(default_factory=list)
    fix_actions: list[FixAction] = field(default_factory=list)


@dataclass
class DiagnosisReport:
    rss_id: int
    rss_url: str
    scanned_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    anime_list: list[AnimeDiagnosis] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class PreviewItem:
    title: str
    bangumi_id: Optional[int] = None
    torrent_count: int = 0
    status: str = "unmatched"  # "matched" | "unmatched" | "unparsed"
```

- [ ] **Step 4: 运行测试确认通过**

- [ ] **Step 5: 提交**

```bash
git add backend/src/module/diagnosis/ backend/src/test/test_diagnosis.py
git commit -m "feat(diagnosis): add data models for RSS diagnosis"
```

---

### Task 2: DiagnosisCollector

**Files:**
- 创建: `backend/src/module/diagnosis/collector.py`
- 修改: `backend/src/test/test_diagnosis.py` — 追加

- [ ] **Step 1: 写 collector 测试**

```python
# 追加到 test_diagnosis.py
from module.diagnosis.collector import DiagnosisCollector
from module.models import Bangumi

def test_collector_record_parse():
    c = DiagnosisCollector()
    c.record_parse("test torrent", None)
    c.record_parse("[Sub] Title S01E01", Bangumi(title_raw="Title"))
    assert len(c._records) == 2
    assert c._records["test torrent"].parse_result is None
    assert c._records["[Sub] Title S01E01"].parse_result is not None

def test_collector_record_match_result():
    c = DiagnosisCollector()
    c.record_match_result("t1", matched=None, filter_passed=None, filter_reason=None)
    c.record_match_result("t2", matched=Bangumi(id=1), filter_passed=True, filter_reason=None)
    assert c._records["t1"].match_result is None
    assert c._records["t2"].match_result is not None
    assert c._records["t2"].filter_passed is True

def test_collector_record_bangumi_create():
    c = DiagnosisCollector()
    c.record_bangumi_create("t1", Bangumi(title_raw="Title"))
    assert c._records["t1"].bangumi_created is True
    c.record_bangumi_create("t2", None, error="Mikan 超时")
    assert c._records["t2"].bangumi_created is False
    assert c._records["t2"].bangumi_create_error == "Mikan 超时"

def test_collector_build_report_groups_by_title_raw():
    c = DiagnosisCollector()
    b1 = Bangumi(title_raw="Title A", id=1)
    b2 = Bangumi(title_raw="Title B")
    c.record_parse("[Sub] Title A S01E01", b1)
    c.record_match_result("[Sub] Title A S01E01", b1, True, None)
    c.record_parse("[Sub] Title A S01E02", b1)
    c.record_match_result("[Sub] Title A S01E02", b1, True, None)
    c.record_parse("[Sub] Title B S01E01", b2)
    c.record_match_result("[Sub] Title B S01E01", None, None, None)

    report = c.build_report(rss_id=1, rss_url="http://test")
    assert len(report.anime_list) == 2
    a_anime = next(a for a in report.anime_list if a.anime_title == "Title A")
    assert len(a_anime.torrents) == 2
    assert a_anime.status == "ok"
    b_anime = next(a for a in report.anime_list if a.anime_title == "Title B")
    assert len(b_anime.torrents) == 1
    assert b_anime.status == "warning"

def test_collector_build_report_filters_by_title():
    c = DiagnosisCollector()
    c.record_parse("t1", Bangumi(title_raw="Keep", id=1))
    c.record_match_result("t1", Bangumi(id=1), True, None)
    c.record_parse("t2", Bangumi(title_raw="Skip"))
    c.record_match_result("t2", None, None, None)
    report = c.build_report(1, "http://test", anime_titles=["Keep"])
    assert len(report.anime_list) == 1
    assert report.anime_list[0].anime_title == "Keep"
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 实现 DiagnosisCollector**

```python
# backend/src/module/diagnosis/collector.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from module.models import Bangumi
from .models import DiagnosisIssue, TorrentDiagnosis, AnimeDiagnosis, DiagnosisReport


@dataclass
class _TorrentRecord:
    torrent_name: str
    parse_result: Optional[Bangumi] = None
    match_result: Optional[Bangumi] = None
    filter_passed: Optional[bool] = None
    filter_reason: Optional[str] = None
    downloaded: bool = False
    bangumi_created: bool = False
    bangumi_create_error: Optional[str] = None


class DiagnosisCollector:
    def __init__(self):
        self._records: dict[str, _TorrentRecord] = {}

    def _get_or_create(self, name: str) -> _TorrentRecord:
        if name not in self._records:
            self._records[name] = _TorrentRecord(torrent_name=name)
        return self._records[name]

    def record_parse(self, name: str, result: Optional[Bangumi]):
        self._get_or_create(name).parse_result = result

    def record_match_result(
        self,
        name: str,
        matched: Optional[Bangumi],
        filter_passed: Optional[bool],
        filter_reason: Optional[str],
    ):
        rec = self._get_or_create(name)
        rec.match_result = matched
        rec.filter_passed = filter_passed
        rec.filter_reason = filter_reason

    def record_download(self, name: str, downloaded: bool):
        self._get_or_create(name).downloaded = downloaded

    def record_bangumi_create(
        self, name: str, bangumi: Optional[Bangumi], error: Optional[str] = None,
    ):
        rec = self._get_or_create(name)
        rec.bangumi_created = bangumi is not None
        rec.bangumi_create_error = error

    def build_report(
        self,
        rss_id: int,
        rss_url: str,
        anime_titles: Optional[list[str]] = None,
    ) -> DiagnosisReport:
        groups: dict[str, list[_TorrentRecord]] = {}
        for rec in self._records.values():
            title = rec.parse_result.title_raw if rec.parse_result else None
            key = title if title else "[unparsed]"
            groups.setdefault(key, []).append(rec)

        anime_list: list[AnimeDiagnosis] = []
        for title, records in groups.items():
            if anime_titles and title not in anime_titles and title != "[unparsed]":
                continue

            bangumi_id = None
            for r in records:
                if r.match_result and r.match_result.id:
                    bangumi_id = r.match_result.id
                    break

            torrents: list[TorrentDiagnosis] = []
            has_error = has_warning = False
            for r in records:
                issues: list[DiagnosisIssue] = []
                if r.parse_result is None:
                    issues.append(DiagnosisIssue("parse", "error", "无法解析种子标题"))
                    has_error = True
                if r.bangumi_create_error:
                    issues.append(DiagnosisIssue("bangumi_create", "warning", r.bangumi_create_error))
                    has_warning = True
                if r.match_result is None and r.parse_result is not None:
                    issues.append(DiagnosisIssue("match", "warning", "未匹配到任何番剧规则"))
                    has_warning = True
                if r.filter_passed is False:
                    issues.append(DiagnosisIssue("filter", "warning", f"被过滤规则排除: {r.filter_reason}"))
                    has_warning = True
                if r.parse_result and r.match_result and not r.downloaded:
                    issues.append(DiagnosisIssue("download", "error", "已匹配但未下载"))
                    has_error = True

                torrents.append(TorrentDiagnosis(
                    torrent_name=r.torrent_name,
                    parse_result=r.parse_result,
                    match_result=r.match_result,
                    filter_passed=r.filter_passed,
                    filter_reason=r.filter_reason,
                    downloaded=r.downloaded,
                    issues=issues,
                ))

            status = "error" if has_error else ("warning" if has_warning else "ok")
            anime_list.append(AnimeDiagnosis(
                anime_title=title, bangumi_id=bangumi_id,
                status=status, torrents=torrents,
            ))

        return DiagnosisReport(rss_id=rss_id, rss_url=rss_url, anime_list=anime_list)
```

- [ ] **Step 4: 运行测试确认通过**

- [ ] **Step 5: 提交**

```bash
git add backend/src/module/diagnosis/collector.py backend/src/test/test_diagnosis.py
git commit -m "feat(diagnosis): implement DiagnosisCollector with grouping"
```

---

### Task 3: 注入 collector 到 raw_parser

**Files:**
- 修改: `backend/src/module/parser/title_parser.py:60-110`

- [ ] **Step 1: 写注入测试**

```python
from module.diagnosis import DiagnosisCollector
from module.parser import TitleParser

def test_raw_parser_with_collector_records_result():
    c = DiagnosisCollector()
    result = TitleParser.raw_parser("[桜都字幕组] 葬送的芙莉莲 S01E01", collector=c)
    assert result is not None
    assert len(c._records) == 1
    rec = list(c._records.values())[0]
    assert rec.parse_result is not None
    assert rec.parse_result.title_raw is not None

def test_raw_parser_without_collector_unchanged():
    result = TitleParser.raw_parser("[桜都字幕组] 葬送的芙莉莲 S01E01")
    assert result is not None
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 修改 raw_parser**

在 `backend/src/module/parser/title_parser.py` 的 `raw_parser` 方法中：
- 签名增加 `collector: DiagnosisCollector | None = None`
- return 前插入: `if collector: collector.record_parse(raw, result)`
- 文件顶部添加 TYPE_CHECKING 导入避免循环引用

- [ ] **Step 4: 运行测试确认通过**

- [ ] **Step 5: 提交**

```bash
git add backend/src/module/parser/title_parser.py backend/src/test/test_diagnosis.py
git commit -m "feat(diagnosis): inject collector into raw_parser"
```

---

### Task 4: 注入 collector 到 match_torrent

**Files:**
- 修改: `backend/src/module/rss/engine.py:134-143`

- [ ] **Step 1: 写注入测试**

```python
def test_engine_match_torrent_unmatched_records_in_collector():
    from module.diagnosis import DiagnosisCollector
    from module.rss.engine import RSSEngine
    from module.models import Torrent

    c = DiagnosisCollector()
    with RSSEngine() as engine:
        t = Torrent(name="[Sub] 不存在的番剧 S99E99", url="magnet:?")
        result = engine.match_torrent(t, collector=c)
    assert result is None
    rec = c._records.get("[Sub] 不存在的番剧 S99E99")
    assert rec is not None
    assert rec.match_result is None
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 修改 RSSEngine.match_torrent**

在 `engine.py:134` 的方法中：
- 签名增加 `collector: DiagnosisCollector | None = None`
- 匹配逻辑后调用 `collector.record_match_result(torrent.name, matched, filter_passed, filter_reason)`
- filter 是排除过滤器: `filter_passed = not bool(pattern.search(torrent.name))` 表示种子没被排除

- [ ] **Step 4: 运行测试确认通过**

- [ ] **Step 5: 提交**

```bash
git add backend/src/module/rss/engine.py backend/src/test/test_diagnosis.py
git commit -m "feat(diagnosis): inject collector into RSSEngine.match_torrent"
```

---

### Task 5: 注入 collector 到 torrents_to_data + refresh_rss

**Files:**
- 修改: `backend/src/module/rss/analyser.py:46-60`
- 修改: `backend/src/module/rss/engine.py:145-173` (refresh_rss)

- [ ] **Step 1: 写注入测试**

```python
@pytest.mark.asyncio
async def test_torrents_to_data_records_bangumi_create():
    from unittest.mock import AsyncMock, patch
    from module.diagnosis import DiagnosisCollector
    from module.rss.analyser import RSSAnalyser
    from module.models import Torrent, RSSItem, Bangumi

    c = DiagnosisCollector()
    analyser = RSSAnalyser()
    torrents = [Torrent(name="[Sub] TestTitle S01E01", url="magnet:?", homepage="https://test")]
    rss = RSSItem(url="https://test/rss", aggregate=True, parser="mikan")

    with patch.object(analyser, 'official_title_parser', new_callable=AsyncMock):
        await analyser.torrents_to_data(torrents, rss, collector=c)
    rec = c._records.get("[Sub] TestTitle S01E01")
    assert rec is not None
    assert rec.bangumi_created is True
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 修改 analyser 和 engine**

`analyser.py` torrents_to_data:
- 签名增加 `collector=None`
- raw_parser 传入 collector
- bangumi.add_all 后调用 `collector.record_bangumi_create()`

`engine.py` refresh_rss:
- 签名增加 `collector=None`
- match_torrent 传入 collector
- add_torrent 后调用 `collector.record_download(torrent.name, True/False)`

- [ ] **Step 4: 运行全部测试**

```bash
cd backend && uv run pytest src/test/ -v
```

- [ ] **Step 5: 提交**

```bash
git add backend/src/module/rss/analyser.py backend/src/module/rss/engine.py backend/src/test/test_diagnosis.py
git commit -m "feat(diagnosis): inject collector into torrents_to_data and refresh_rss"
```

---

### Task 6: DiagnosisService

**Files:**
- 创建: `backend/src/module/diagnosis/service.py`

- [ ] **Step 1: 写服务测试**

```python
@pytest.mark.asyncio
async def test_preview_groups_torrents_by_title():
    from unittest.mock import AsyncMock, MagicMock, patch
    from module.diagnosis.service import DiagnosisService
    from module.models import Torrent, RSSItem, Bangumi

    service = DiagnosisService()
    with patch("module.diagnosis.service.RSSEngine") as MockEngine, \
         patch("module.diagnosis.service.TitleParser") as MockParser:
        mock_engine = MagicMock()
        MockEngine.return_value.__enter__ = MagicMock(return_value=mock_engine)
        MockEngine.return_value.__exit__ = MagicMock(return_value=False)
        rss = RSSItem(id=1, url="https://test/rss", aggregate=True)
        mock_engine.rss.search_id.return_value = rss
        MockEngine._get_torrents = AsyncMock(return_value=[
            Torrent(name="[Sub] A S01E01", url="m1"),
            Torrent(name="[Sub] A S01E02", url="m2"),
            Torrent(name="[Sub] B S01E01", url="m3"),
        ])
        MockParser.raw_parser.side_effect = [
            Bangumi(title_raw="A"), Bangumi(title_raw="A"), Bangumi(title_raw="B"),
        ]
        mock_engine.bangumi.match_torrent.side_effect = [
            Bangumi(id=1, title_raw="A"), Bangumi(id=1, title_raw="A"), None,
        ]
        items = await service.preview(1)
    assert len(items) == 2
    a = next(i for i in items if i.title == "A")
    assert a.torrent_count == 2
    assert a.status == "matched"
    b = next(i for i in items if i.title == "B")
    assert b.status == "unmatched"
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 实现 DiagnosisService**

核心实现要点：

`preview`: 拉取 RSS → raw_parser → 按 title_raw 分组 → 查 bangumi 表匹配状态

`diagnose`: 拉取 RSS → 创建 collector → 执行完整链路 → 对聚合 RSS 检查 bangumi 创建状态 → 查下载状态 → build_report

`fix`: 按 action 分发：
- `force_download`: `DownloadClient.add_torrent()`
- `link_bangumi`: 更新 `torrent.bangumi_id`
- `fix_parse`: 创建/更新 bangumi 记录
- `edit_filter`: 更新 bangumi.filter

注意区分聚合/普通 RSS：聚合 RSS 的 diagnose 额外检查 `rss.aggregate` 并调用 `collector.record_bangumi_create`。

参考 spec 文件中 "API 端点详情" 和 "Fix 端点详情" 部分的完整设计。

- [ ] **Step 4: 运行测试确认通过**

- [ ] **Step 5: 提交**

```bash
git add backend/src/module/diagnosis/service.py backend/src/test/test_diagnosis.py
git commit -m "feat(diagnosis): implement DiagnosisService"
```

---

### Task 7: API 端点

**Files:**
- 创建: `backend/src/module/api/diagnosis.py`
- 修改: `backend/src/module/api/__init__.py`

- [ ] **Step 1: 创建 API 路由**

```python
# backend/src/module/api/diagnosis.py
from fastapi import APIRouter, Depends
from module.diagnosis.service import DiagnosisService
from module.security.api import UNAUTHORIZED, get_current_user

# 挂在 /rss/{id}/diagnosis 下，与 rss 路由共用前缀
router = APIRouter(prefix="/rss", tags=["diagnosis"])

@router.get(
    "/{rss_id}/diagnosis/preview",
    dependencies=[Depends(get_current_user)],
)
async def preview(rss_id: int):
    items = await DiagnosisService().preview(rss_id)
    return {"data": [vars(i) for i in items]}

@router.post(
    "/{rss_id}/diagnosis/scan",
    dependencies=[Depends(get_current_user)],
)
async def scan(rss_id: int, body: dict):
    report = await DiagnosisService().diagnose(rss_id, body.get("anime_titles", []))
    return {"data": vars(report)}

# 修复操作独立前缀
fix_router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])

@fix_router.post(
    "/fix",
    dependencies=[Depends(get_current_user)],
)
async def fix(body: dict):
    from module.diagnosis.models import FixAction
    result = await DiagnosisService().fix(FixAction(**body))
    return {"data": {"success": result}}
```

- [ ] **Step 2: 在 `backend/src/module/api/__init__.py` 注册路由**

```python
# 在 import 区域添加:
from .diagnosis import router as diagnosis_router, fix_router as diagnosis_fix_router

# 在 v1.include_router 区域添加:
v1.include_router(diagnosis_router)
v1.include_router(diagnosis_fix_router)
```

完整路径：
- `GET /api/v1/rss/{id}/diagnosis/preview`
- `POST /api/v1/rss/{id}/diagnosis/scan`
- `POST /api/v1/diagnosis/fix`

- [ ] **Step 3: 手动验证端点可达**

```bash
cd backend/src && uv run python main.py
# 访问 /docs 查看 diagnosis 端点
```

- [ ] **Step 4: 提交**

```bash
git add backend/src/module/api/diagnosis.py backend/src/module/api/__init__.py
git commit -m "feat(diagnosis): add API endpoints"
```

---

### Task 8: 前端 API 客户端

**Files:**
- 创建: `webui/src/api/diagnosis.ts`

- [ ] **Step 1: 创建类型和 API 方法**

```typescript
// webui/src/api/diagnosis.ts
// 项目使用全局注册的 axios，不需要 import

export interface PreviewItem {
  title: string;
  bangumi_id: number | null;
  torrent_count: number;
  status: 'matched' | 'unmatched' | 'unparsed';
}

export interface DiagnosisIssue {
  step: string;
  severity: string;
  message: string;
}

export interface TorrentDiagnosis {
  torrent_name: string;
  parse_result: any | null;
  match_result: any | null;
  filter_passed: boolean | null;
  filter_reason: string | null;
  downloaded: boolean;
  issues: DiagnosisIssue[];
}

export interface AnimeDiagnosis {
  anime_title: string;
  bangumi_id: number | null;
  status: 'ok' | 'warning' | 'error';
  torrents: TorrentDiagnosis[];
  fix_actions: FixAction[];
}

export interface FixAction {
  action: string;
  torrent_name: string;
  params: Record<string, any>;
}

export interface DiagnosisReport {
  rss_id: number;
  rss_url: string;
  scanned_at: string;
  anime_list: AnimeDiagnosis[];
  errors: string[];
}

export const apiDiagnosis = {
  async preview(rssId: number) {
    const { data } = await axios.get(`api/v1/rss/${rssId}/diagnosis/preview`);
    return data!.data as PreviewItem[];
  },
  async scan(rssId: number, animeTitles: string[]) {
    const { data } = await axios.post(`api/v1/rss/${rssId}/diagnosis/scan`, {
      anime_titles: animeTitles,
    });
    return data!.data as DiagnosisReport;
  },
  async fix(action: FixAction) {
    const { data } = await axios.post('api/v1/diagnosis/fix', action);
    return data!.data as { success: boolean };
  },
};
```

- [ ] **Step 2: 提交**

```bash
git add webui/src/api/diagnosis.ts
git commit -m "feat(diagnosis): add frontend API client"
```

---

### Task 9: 诊断 Modal 组件

**Files:**
- 创建: `webui/src/components/ab-rss-diagnosis.vue`
- 修改: `webui/src/pages/index/rss.vue`

- [ ] **Step 1: 实现 Modal 组件**

三阶段状态机: selecting → scanning → result

- selecting: 调用 preview API，展示番剧列表 + 勾选框（unmatched/unparsed 默认选中，matched 默认不选）
- scanning: loading
- result: 按番剧分组展示诊断链路（非 ok 默认展开），颜色编码（绿/黄/红），修复操作按钮

使用 `ab-popup` 容器，参考 `ab-add-rss.vue` 模式。

- [ ] **Step 2: 在 RSS 页面添加诊断按钮**

修改 `webui/src/pages/index/rss.vue`：
- 每个 RSS 条目添加"诊断"按钮
- 点击后显示 `ab-rss-diagnosis` 组件

- [ ] **Step 3: 手动测试**

```bash
cd webui && pnpm dev
```

- [ ] **Step 4: 提交**

```bash
git add webui/src/components/ab-rss-diagnosis.vue webui/src/pages/index/rss.vue
git commit -m "feat(diagnosis): add diagnosis modal"
```

---

### Task 10: i18n

**Files:**
- 修改: `webui/src/i18n/zh-CN.json`
- 修改: `webui/src/i18n/en.json`

- [ ] **Step 1: 添加翻译键**

在两个文件中添加 `diagnosis` 节点：

```json
"diagnosis": {
  "title": "RSS 诊断",
  "select_anime": "选择要诊断的番剧",
  "start": "开始诊断",
  "scanning": "正在扫描...",
  "step_parse": "解析",
  "step_match": "匹配",
  "step_filter": "过滤",
  "step_download": "下载",
  "status_ok": "正常",
  "status_warning": "警告",
  "status_error": "错误",
  "filter_passed": "通过",
  "filter_blocked": "被排除",
  "not_downloaded": "未下载",
  "no_match": "未匹配",
  "parse_failed": "解析失败",
  "fix_force_download": "强制下载",
  "fix_link_bangumi": "关联番剧",
  "fix_edit_parse": "修正解析",
  "fix_edit_filter": "调整过滤规则",
  "preview_matched": "已匹配",
  "preview_unmatched": "未匹配",
  "preview_unparsed": "解析失败",
  "torrent_count": "{count} 个种子",
  "no_anime_found": "未找到番剧"
}
```

- [ ] **Step 2: 在组件中替换硬编码文字**

- [ ] **Step 3: 提交**

```bash
git add webui/src/i18n/
git commit -m "feat(diagnosis): add i18n strings"
```

---

### Task 11: 端到端验证

- [ ] **Step 1: 运行全部后端测试**

```bash
cd backend && uv run pytest src/test/ -v
```

- [ ] **Step 2: 前端类型检查**

```bash
cd webui && pnpm test:build
```

- [ ] **Step 3: 手动测试完整流程**

启动前后端，在 RSS 页面测试诊断功能。

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat(diagnosis): complete RSS diagnosis feature"
```
