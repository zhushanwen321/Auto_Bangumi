# RSS 番剧诊断功能设计

> 日期: 2026-04-06
> 分支: feat/rss-diagnosis (基于 main)
> 状态: 设计中

---

## 背景

用户反馈 RSS 订阅中部分番剧无法自动加入 bangumi list，或种子无法自动下载。现有代码缺乏错误反馈——匹配失败后无重试路径，用户无法得知失败原因。GitHub 上有大量相关 issue（#909、#770、#733、#1012、#818）。

## 目标

在 RSS 管理页面提供诊断入口，让用户能够：
1. 选择 RSS 源中的特定番剧
2. 实时扫描 RSS，查看每个种子的完整匹配链路
3. 发现问题后直接执行修复操作

## 设计决策

### 为什么选择"注入收集器"而非独立诊断逻辑

两套独立代码必然产生行为差异——诊断说"应该匹配成功"，实际流程却失败。注入 `DiagnosisCollector` 到现有函数中，诊断流程和正常流程走完全相同的代码路径，`collector=None` 时零开销。

### 为什么选择一次性批量诊断

RSS 下番剧数量通常 10-30 部，实时扫描耗时可接受。SSE 流式推送需要新基础设施，收益不足以覆盖成本。

### RSS 类型差异

系统中存在两种 RSS，诊断逻辑需要分别处理：

| | 聚合 RSS（aggregate=True） | 普通 RSS（aggregate=False） |
|---|---|---|
| 典型来源 | Mikan "我的番组" | 单番剧订阅链接 |
| 内容 | 多部番剧的种子 | 通常一部番剧的种子 |
| rss_to_data | 会执行，创建 bangumi 记录 | 不执行 |
| refresh_rss | 会执行，匹配+下载 | 会执行，匹配+下载 |
| 诊断场景 | "为什么没创建 bangumi 记录" + "为什么没下载" | "为什么没匹配/下载" |

诊断入口统一在 RSS 管理页面，后端根据 `rss.aggregate` 字段自动调整诊断链路：

- **聚合 RSS**：完整诊断链路（解析→bangumi 创建→匹配→过滤→下载）
- **普通 RSS**：简化诊断链路（解析→匹配→过滤→下载，跳过 bangumi 创建检查）

---

## 架构

### 数据结构

```python
@dataclass
class DiagnosisIssue:
    step: str          # "parse" | "bangumi_create" | "match" | "filter" | "download"
    severity: str      # "warning" | "error"
    message: str       # 人类可读的描述

@dataclass
class TorrentDiagnosis:
    torrent_name: str
    # raw_parser 解析结果，None 表示解析失败
    parse_result: Bangumi | None
    # 匹配+过滤的联合结果（match_torrent 内部同时做两步）
    match_result: Bangumi | None     # 匹配到的 bangumi，None 表示未匹配
    filter_passed: bool | None       # True=种子没有被排除过滤掉
    filter_reason: str | None        # 如果被过滤，说明匹配到了哪个关键词
    downloaded: bool
    issues: list[DiagnosisIssue]

@dataclass
class AnimeDiagnosis:
    anime_title: str                 # 按 title_raw 聚合后的番剧标题
    bangumi_id: int | None           # None 表示数据库中无此番剧记录
    status: str                      # "ok" | "warning" | "error"
    torrents: list[TorrentDiagnosis]
    fix_actions: list[FixAction]

@dataclass
class DiagnosisReport:
    rss_id: int
    rss_url: str
    scanned_at: datetime             # UTC
    anime_list: list[AnimeDiagnosis]
    errors: list[str]                # RSS 不可达等全局错误

@dataclass
class FixAction:
    action: str
    torrent_name: str
    params: dict                     # 各 action 的参数 schema 见下方
```

### 分组规则

诊断报告按种子的 `title_raw`（raw_parser 解析出的原始标题）聚合为番剧组。特殊分组：
- 解析失败的种子 → `anime_title = "[解析失败]"`，`bangumi_id = None`
- 解析成功但无 title_raw → `anime_title = torrent_name`

### 过滤语义

项目中的 `filter` 字段是**排除过滤器**。`match_torrent` 中的逻辑：
```python
if not pattern.search(torrent.name):  # 种子名不匹配过滤关键词 → 通过
    return matched
```
即 `filter_passed=True` 表示种子**没有被排除**。诊断报告中需要明确说明这个语义。

### DiagnosisCollector

```python
class DiagnosisCollector:
    def record_parse(self, torrent_name: str, result: Bangumi | None):
        """记录 raw_parser 解析结果"""

    def record_match_result(
        self,
        torrent_name: str,
        matched: Bangumi | None,
        filter_passed: bool | None,
        filter_reason: str | None,
    ):
        """记录 match_torrent 的联合结果（匹配+过滤在同一步）"""

    def record_download(self, torrent_name: str, downloaded: bool):
        """记录下载状态"""

    def record_bangumi_create(
        self, torrent_name: str, bangumi: Bangumi | None, error: str | None = None
    ):
        """仅聚合 RSS：记录 bangumi 记录创建结果（rss_to_data 链路）"""

    def build_report(self, anime_titles: list[str] | None = None) -> DiagnosisReport:
        """汇总生成报告，anime_titles 为 None 时返回全部"""
```

### API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/rss/{id}/diagnosis/preview` | 快速返回 RSS 下番剧列表 |
| POST | `/api/v1/rss/{id}/diagnosis` | 实时扫描诊断 |
| POST | `/api/v1/diagnosis/fix` | 执行修复操作 |

#### Preview 端点详情

返回数据结构：
```python
@dataclass
class PreviewItem:
    title: str              # 番剧标题（title_raw 或 bangumi.official_title）
    bangumi_id: int | None  # 已有记录的 ID
    torrent_count: int      # 该标题下种子数量
    status: str             # "matched" | "unmatched" | "unparsed"
```

实现策略：
- **聚合 RSS**：实时拉取 RSS → raw_parser 解析每个种子 → 按 title_raw 分组 → 与 bangumi 表比对
- **普通 RSS**：查 bangumi 表中 rss_link 匹配该 RSS URL 的记录 + 查 torrent 表中 rss_id 匹配但 bangumi_id 为空的种子

#### Diagnosis 端点详情

```python
# Request
{
    "anime_titles": ["葬送的芙莉莲", "最强的职业不是勇者"]  # 空=诊断全部
}

# Response: DiagnosisReport（见数据结构）
```

实现：拉取 RSS → 对每个种子执行解析+匹配+过滤 → 按选中番剧过滤结果 → 返回报告。

#### Fix 端点详情

```python
# Request
{
    "action": "force_download",
    "params": {
        "torrent_url": "magnet:...",
        "bangumi_id": 42
    }
}
```

各 action 的 params schema：

| Action | Params | 执行逻辑 |
|--------|--------|---------|
| `force_download` | `{ torrent_url, bangumi_id }` | 调用 `DownloadClient.add_torrent`，写 torrent 记录 |
| `link_bangumi` | `{ torrent_id, bangumi_id }` | 更新 `torrent.bangumi_id`，不触发 refresh |
| `fix_parse` | `{ torrent_name, title_raw, season, episode }` | 创建/更新 bangumi 记录（用修正后的解析结果） |
| `edit_filter` | `{ bangumi_id, filter }` | 调用现有 `PUT /api/v1/bangumi/{id}` 更新 filter |

### 现有函数改造

在以下函数签名中增加可选的 `collector` 参数：

```python
# TitleParser.raw_parser
def raw_parser(self, raw: str, collector: DiagnosisCollector | None = None) -> Bangumi | None:
    result = ...  # 原有逻辑
    if collector:
        collector.record_parse(raw, result)
    return result

# RSSEngine.match_torrent — 同时记录匹配和过滤
def match_torrent(self, torrent: Torrent, collector: DiagnosisCollector | None = None) -> Bangumi | None:
    matched = self.bangumi.match_torrent(torrent.name)
    filter_passed = None
    filter_reason = None
    if matched:
        if matched.filter:
            pattern = self._get_filter_pattern(matched.filter)
            filter_passed = not bool(pattern.search(torrent.name))
            filter_reason = matched.filter if not filter_passed else None
        else:
            filter_passed = True
    if collector:
        collector.record_match_result(torrent.name, matched, filter_passed, filter_reason)
    # 原有返回逻辑不变
    ...

# RSSAnalyser.torrents_to_data — 仅聚合 RSS 使用
async def torrents_to_data(self, torrents, rss, full_parse=True, collector=None):
    for torrent in torrents:
        bangumi = self.raw_parser(raw=torrent.name, collector=collector)
        if bangumi and bangumi.title_raw not in seen_titles:
            await self.official_title_parser(...)
            if collector:
                collector.record_bangumi_create(torrent.name, bangumi)
            ...
```

`collector=None` 时行为完全不变。

### 并发安全

诊断 API 与后台 `rss_loop` 可能同时运行。诊断流程**只读不写**（preview 和 diagnosis 端点不修改数据库），不存在写入冲突。Fix 端点的修改操作（更新 bangumi_id、filter 等）是单行操作，SQLite 的 WAL 模式足以处理。

---

## 前端交互

### 入口

RSS 管理页面，每个 RSS 条目旁新增"诊断"按钮。

### Modal 三阶段

1. **选择番剧** — 调用 preview 端点，展示番剧列表 + 状态标签 + 勾选框
   - 默认全选"unmatched"和"unparsed"项
   - "matched"项默认不选
2. **扫描中** — 调用 diagnosis 端点，显示 loading（带进度提示"正在扫描 X/Y"）
3. **展示结果** — 按番剧分组，显示完整诊断链路
   - 每个番剧默认折叠，点击展开查看详情
   - 只有 status != "ok" 的番剧默认展开
   - 大量结果时提供搜索/筛选

### 诊断结果展示

颜色编码：绿色=正常，黄色=警告，红色=错误。

每个番剧下显示完整链路：
```
▸ 解析: [标题] S01E03  ← 绿色/红色
▸ bangumi 记录: 已存在 #42  ← 仅聚合 RSS
▸ 匹配: title_raw 匹配 "葬送的芙莉莲"  ← 绿色/红色
▸ 过滤: 通过 / 被排除（匹配关键词 "1080p"）  ← 绿色/黄色
▸ 下载: 已下载  ← 绿色/红色
```

### 修复操作

| 操作 | 触发条件 | 交互 |
|------|---------|------|
| 强制下载种子 | 过滤排除或匹配成功但未下载 | 确认后直接调用 |
| 手动关联番剧 | 解析成功但未匹配到 bangumi | 弹出番剧搜索选择器 |
| 修正解析结果 | 解析失败或结果有误 | 弹出编辑表单（标题、季度、集数） |
| 调整过滤规则 | 种子被过滤排除 | 弹出过滤规则编辑器 |

---

## 错误场景覆盖

| 场景 | step | severity | message |
|------|------|----------|---------|
| raw_parser 返回 None | parse | error | "无法解析种子标题" |
| mikan_parser 网络超时 | bangumi_create | warning | "Mikan 页面获取失败，使用降级标题" |
| match_torrent 无匹配 | match | warning | "未匹配到任何番剧规则" |
| filter 排除种子 | filter | warning | "被过滤规则 '{filter}' 排除" |
| 下载客户端连接失败 | download | error | "下载客户端不可用" |
| 种子 URL 无效 | download | error | "种子 URL 无法访问" |
| RSS URL 不可达 | 全局 | error | report.errors 中记录 |

---

## 不做什么

- 不做 SSE 流式诊断
- 不做定时自动诊断
- 不修改现有正常流程的行为
- 不依赖 torrent-management 分支的代码
- 诊断过程不暂停 rss_loop（只读不写，无冲突）
