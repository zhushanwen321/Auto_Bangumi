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
2. 实时扫描 RSS，查看每个种子的完整匹配链路（解析→匹配→过滤→下载）
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

preview 端点也需区分：
- 聚合 RSS：列出所有检测到的番剧标题（已匹配 + 未匹配）
- 普通 RSS：列出关联的 bangumi（如已关联）+ 未匹配种子

---

## 架构

### 数据结构

```python
@dataclass
class DiagnosisIssue:
    step: str          # "parse" | "match" | "filter" | "download"
    severity: str      # "warning" | "error"
    message: str       # 人类可读的描述

@dataclass
class TorrentDiagnosis:
    torrent_name: str
    parse_result: ParsedTitle | None
    match_result: Bangumi | None
    filter_passed: bool | None
    filter_reason: str | None
    downloaded: bool
    issues: list[DiagnosisIssue]

@dataclass
class AnimeDiagnosis:
    anime_title: str
    bangumi_id: int | None
    status: str         # "ok" | "warning" | "error"
    torrents: list[TorrentDiagnosis]
    fix_actions: list[FixAction]

@dataclass
class DiagnosisReport:
    rss_id: int
    rss_url: str
    scanned_at: datetime
    anime_list: list[AnimeDiagnosis]

@dataclass
class FixAction:
    action: str          # "force_download" | "link_bangumi" | "fix_parse" | "edit_filter"
    torrent_name: str
    params: dict
```

### DiagnosisCollector

```python
class DiagnosisCollector:
    def record_parse(self, torrent_name: str, result): ...
    def record_match(self, torrent_name: str, matched): ...
    def record_filter(self, torrent_name: str, passed: bool, reason: str): ...
    def record_download(self, torrent_name: str, downloaded: bool): ...
    def build_report(self, anime_titles: list[str]) -> DiagnosisReport: ...
```

### API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/rss/{id}/diagnosis/preview` | 快速返回 RSS 下番剧列表（数据库聚合） |
| POST | `/api/v1/rss/{id}/diagnosis` | 实时扫描诊断，body: `{ anime_titles: string[] }` |
| POST | `/api/v1/diagnosis/fix` | 执行修复操作 |

### 现有函数改造

在以下函数签名中增加可选的 `collector` 参数：

- `raw_parser(raw, collector=None)` — 记录解析结果
- `RSSEngine.match_torrent(torrent, collector=None)` — 记录匹配结果
- 过滤检查逻辑 — 记录过滤原因

`collector=None` 时行为完全不变。

---

## 前端交互

### 入口

RSS 管理页面，每个 RSS 条目旁新增"诊断"按钮。

### Modal 三阶段

1. **选择番剧** — 调用 preview 端点，展示番剧列表 + 状态标签 + 勾选框
2. **扫描中** — 调用 diagnosis 端点，显示 loading
3. **展示结果** — 按番剧分组，显示完整诊断链路

### 诊断结果展示

颜色编码：绿色=正常，黄色=警告，红色=错误。
每个有问题的番剧下方提供修复按钮。

### 修复操作

| 操作 | 交互 |
|------|------|
| 强制下载种子 | 直接调用 recollect-by-urls |
| 手动关联番剧 | 弹出番剧搜索选择器 |
| 修正解析结果 | 弹出编辑表单 |
| 调整过滤规则 | 弹出过滤规则编辑器 |

---

## 不做什么

- 不做 SSE 流式诊断
- 不做定时自动诊断
- 不修改现有正常流程的行为
- 不依赖 torrent-management 分支的代码
